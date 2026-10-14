"""Responsive desktop companion for the explicitly supported editor operations.

All Tk access stays on the main thread. Editor work and optional dictation run
in one worker at a time. Every operation captures its cancellation lease before
it is dispatched; dictation only fills the command field.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .runtime import Controller
from .windows import StopHotkey, dictate_once, voice_available
from .config import load_config, save_config
from .logsetup import setup_logging
from . import voice as voice_mod
from .assistant import understand
from .nlu import strip_wake_word
from .live import LiveControlError
from .actions import Action, ActionError, Executor, MacroStore
from .knowledge import KnowledgeBase
from .feedback import Speaker, install_crash_logging, load_user_env, set_start_with_windows, set_user_env
from .workflows import CHEATSHEET
from . import __version__
import logging

log = logging.getLogger(__name__)
MODE_LABELS = {"auto": "Auto (online → local)", "local": "Local / offline", "online": "Online (free tier)"}


BG = "#111827"
PANEL = "#182235"
TEXT = "#e6edf7"
MUTED = "#a6b5c9"
ACCENT = "#93c5fd"


def default_resource_directory() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "resources"


def initial_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Fit Tk's reported screen coordinates, including virtualized DPI layouts."""
    return max(1, min(1180, screen_width - 80)), max(1, min(850, screen_height - 110))


def timeline_rows(snapshot: dict) -> list[dict]:
    """Flatten an actual inspection while retaining exact editor identities."""
    rows = []
    if snapshot.get("editor") == "kdenlive":
        for sequence in snapshot.get("sequences", []):
            for track in sequence.get("tracks", []):
                for playlist in track.get("playlists", []):
                    for instance in playlist.get("instances", []):
                        rows.append({**instance, "sequence_name": sequence.get("name", sequence.get("id", "")),
                                     "track_name": track.get("name", track.get("id", "")),
                                     "track_locked": bool(track.get("locked"))})
    else:
        for clip in snapshot.get("clips", []):
            rows.append({**clip, "instance_id": clip.get("id"),
                         "timeline_in": clip.get("start_frame"),
                         "timeline_out_exclusive": clip.get("end_frame"),
                         "track_name": f"{str(clip.get('track_type', '')).title()} {clip.get('track', '')}",
                         "sequence_name": snapshot.get("identity", {}).get("timeline_name", "")})
    return rows


def find_kdenlive_executable() -> Path | None:
    """Locate standard installed editor executables; never invoke a shell."""
    candidates = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.extend((Path(base) / "kdenlive/bin/kdenlive.exe", Path(base) / "kdenlive/kdenlive.exe"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.extend((Path(local) / "Programs/kdenlive/bin/kdenlive.exe", Path(local) / "Programs/kdenlive/kdenlive.exe"))
    if os.name == "nt":
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\kdenlive.exe") as key:
                    value, kind = winreg.QueryValueEx(key, None)
                    if isinstance(value, str):
                        candidate = Path(value.strip('"'))
                        if candidate.name.casefold() == "kdenlive.exe":
                            candidates.append(candidate)
            except OSError:
                pass
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def validate_report_destination(destination: Path, protected_paths=()) -> None:
    if destination.suffix.casefold() != ".json":
        raise ValueError("Inspection reports must use a .json filename. Project and media files cannot be overwritten.")
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("The report destination must be a regular file, not a link or directory.")
    resolved = destination.resolve()
    if any(resolved == Path(protected).resolve() for protected in protected_paths):
        raise ValueError("The report destination is a project or source asset. Choose a separate .json file.")


def save_report_atomic(destination: Path, serialized: str, lease, protected_paths=()) -> None:
    """Write completely, then publish; never use a project/media file as output."""
    validate_report_destination(destination, protected_paths)
    lease.assert_active()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".copilot-report-", suffix=".tmp", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        lease.assert_active()
        validate_report_destination(destination, protected_paths)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class CopilotApp:
    def __init__(self, root: tk.Tk, controller: Controller, resource_dir: Path | str | None = None,
                 *, load_demo: bool = True, enable_hotkey: bool = True):
        self.root, self.controller = root, controller
        self.resource_dir = Path(resource_dir) if resource_dir is not None else default_resource_directory()
        self.messages: queue.Queue = queue.Queue()
        self._active_thread: threading.Thread | None = None
        self._busy = False
        self._closing = False
        self._closed_controller = False
        self._close_started = 0.0
        self._voice_cancel = threading.Event()
        self._snapshot: dict | None = None
        self._snapshot_time: str | None = None
        self._row_ids: dict[str, str | None] = {}
        self._row_data: dict[str, dict] = {}
        self._last_output: Path | None = None
        self._preview_text: str | None = None
        self._selected_instance_at_preview: str | None = None
        self._hotkey = None
        self._voice_checked = False
        self._voice_available = False
        self._voice_reason = "Checking optional Windows dictation…"
        self._after_ids: set[str] = set()
        self._listener = None
        try:
            self.config, self.config_warnings = load_config(controller.directory)
            setup_logging(controller.directory, self.config["logging"]["level"],
                          self.config["logging"]["max_bytes"], self.config["logging"]["backups"])
        except Exception:  # configuration must never block the editor companion
            from .config import DEFAULTS
            self.config, self.config_warnings = copy.deepcopy(DEFAULTS), ["Configuration could not be loaded."]
        try:
            install_crash_logging(controller.directory)
            self.root.report_callback_exception = lambda t, e, tb: install_crash_logging.write("tk callback", t, e, tb)
        except Exception:
            pass
        load_user_env([self.config["online"]["groq_api_key_env"], self.config["online"]["gemini_api_key_env"]])
        self.speaker = Speaker(self.config["ui"]["feedback"])
        self._overlay = None
        self.macros = MacroStore(controller.directory / "macros.json")
        self._executor = None
        self._kb = None
        self.mode = tk.StringVar(value=MODE_LABELS[self.config["mode"]])
        self.voice_state = tk.StringVar(value="Hands-free: off")

        self.editor = tk.StringVar(value="Kdenlive" if controller.editor == "kdenlive" else "DaVinci Resolve")
        self.command = tk.StringVar(value='add guide at frame 10 named "Review point"')
        self.status = tk.StringVar(value="Ready")
        self.project_label = tk.StringVar(value="Open a saved project to begin")
        self.scope_label = tk.StringVar()
        self.selection_label = tk.StringVar(value="No timeline clip selected")
        self._build()
        self.command.trace_add("write", self._command_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Control-Return>", lambda event: self.preview_command())
        self.root.bind("<Control-Shift-space>", lambda event: self.stop())
        self.root.bind("<Escape>", lambda event: self.stop())
        if enable_hotkey:
            self._hotkey = StopHotkey(self._hotkey_stop)
        self._schedule(40, self._poll)
        self._set_scope()
        self._update_buttons()
        self.root.title(f"Editing Copilot {__version__}")
        if enable_hotkey:  # real app (tests pass enable_hotkey=False)
            self._schedule(300, self._first_run)
        if load_demo and controller.path is None and controller.editor == "kdenlive":
            self._schedule(100, self._startup_demo)
        else:
            self._schedule(100, self._probe_voice)

    def _schedule(self, milliseconds, callback):
        token = None

        def run():
            self._after_ids.discard(token)
            callback()
        token = self.root.after(milliseconds, run)
        self._after_ids.add(token)
        return token

    def _build(self):
        self.root.title("Editing Copilot · Verified editing companion")
        width, height = initial_window_size(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(930, width), min(720, height))
        self.root.configure(bg=BG)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 23))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Accent.TLabel", foreground=ACCENT, font=("Segoe UI Semibold", 10))
        style.configure("TButton", background="#27364c", foreground=TEXT, padding=(13, 8), borderwidth=0)
        style.map("TButton", background=[("active", "#354c68"), ("disabled", "#1c293c")], foreground=[("disabled", "#718096")])
        style.configure("Primary.TButton", background="#2563eb", foreground="white")
        style.map("Primary.TButton", background=[("active", "#3b82f6"), ("disabled", "#223657")])
        style.configure("Stop.TButton", background="#8d3342", foreground="white")
        style.map("Stop.TButton", background=[("active", "#ad4254")])
        style.configure("TEntry", fieldbackground="#243246", foreground=TEXT, padding=10)
        style.configure("TCombobox", fieldbackground="#243246", foreground=TEXT, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#243246")], foreground=[("readonly", TEXT)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#243246", foreground=MUTED, padding=(18, 9))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", TEXT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=29, borderwidth=0)
        style.configure("Treeview.Heading", background="#243246", foreground=TEXT, padding=7, font=("Segoe UI Semibold", 10))
        style.map("Treeview", background=[("selected", "#255291")], foreground=[("selected", "white")])

        outer = ttk.Frame(self.root, padding=(24, 19))
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Editing Copilot", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="A clear plan. A deliberate edit. A recorded result.", style="Muted.TLabel").pack(anchor="w", pady=(2, 16))

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Editor").pack(side="left", padx=(0, 10))
        self.editor_box = ttk.Combobox(toolbar, textvariable=self.editor, values=("Kdenlive", "DaVinci Resolve"), state="readonly", width=19)
        self.editor_box.pack(side="left")
        self.editor_box.bind("<<ComboboxSelected>>", self._editor_changed)
        self.open_button = ttk.Button(toolbar, text="Open saved project", command=self.open_project)
        self.open_button.pack(side="left", padx=(12, 6))
        self.demo_button = ttk.Button(toolbar, text="Demo project", command=self._startup_demo)
        self.demo_button.pack(side="left", padx=(0, 6))
        self.inspect_button = ttk.Button(toolbar, text="Inspect", command=self.inspect_project)
        self.inspect_button.pack(side="left", padx=(0, 6))
        self.tools_button = ttk.Menubutton(toolbar, text="Tools")
        self.tools_button.pack(side="left", padx=(0, 6))
        self.tools_menu = tk.Menu(self.tools_button, tearoff=False, bg=PANEL, fg=TEXT, activebackground="#255291", activeforeground="white")
        self.tools_menu.add_command(label="Install Resolve menu for my account", command=lambda: self._install_action("resolve"))
        self.tools_menu.add_command(label="Install companion for my account", command=lambda: self._install_action("companion"))
        self.tools_menu.add_separator()
        self.tools_menu.add_command(label="What can I say? (cheat sheet)", command=self.open_cheatsheet)
        self.tools_menu.add_command(label="Setup wizard…", command=self.open_wizard)
        self.tools_menu.add_command(label="Show/hide status overlay", command=self.toggle_overlay)
        self.tools_menu.add_command(label="Voice macros…", command=self.open_macro_editor)
        self.tools_menu.add_command(label="List controls of the editor window", command=self.list_editor_controls)
        self.tools_button.configure(menu=self.tools_menu)
        self.stop_button = ttk.Button(toolbar, text="Stop  ·  Ctrl+Shift+Space", style="Stop.TButton", command=self.stop)
        self.stop_button.pack(side="right")
        self.path_label_widget = ttk.Label(outer, textvariable=self.project_label, style="Accent.TLabel", wraplength=1090)
        self.path_label_widget.pack(anchor="w", pady=(12, 5))
        ttk.Label(outer, textvariable=self.scope_label, style="Muted.TLabel", wraplength=1090).pack(anchor="w", pady=(0, 15))

        command_bar = ttk.Frame(outer)
        command_bar.pack(fill="x")
        ttk.Label(command_bar, text="Command", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        command_row = ttk.Frame(command_bar)
        command_row.pack(fill="x")
        self.command_entry = ttk.Entry(command_row, textvariable=self.command, font=("Segoe UI", 12))
        self.command_entry.pack(side="left", fill="x", expand=True)
        self.command_entry.bind("<Return>", lambda event: self.preview_command())
        self.dictate_button = ttk.Button(command_row, text="Dictate", command=self.dictate)
        self.dictate_button.pack(side="left", padx=(8, 0))
        self.handsfree_button = ttk.Button(command_row, text="Hands-free voice", command=self.toggle_handsfree)
        self.handsfree_button.pack(side="left", padx=(8, 0))
        self.mode_box = ttk.Combobox(command_row, textvariable=self.mode, values=tuple(MODE_LABELS.values()), state="readonly", width=21)
        self.mode_box.pack(side="left", padx=(8, 0))
        self.mode_box.bind("<<ComboboxSelected>>", self._mode_changed)
        ttk.Label(command_bar, textvariable=self.voice_state, style="Accent.TLabel").pack(anchor="w", pady=(4, 0))
        action_row = ttk.Frame(command_bar)
        action_row.pack(fill="x", pady=(9, 8))
        self.preview_button = ttk.Button(action_row, text="Preview command", command=self.preview_command)
        self.preview_button.pack(side="left", padx=(0, 7))
        self.apply_button = ttk.Button(action_row, text="Apply preview", style="Primary.TButton", command=self.apply_preview)
        self.apply_button.pack(side="left", padx=(0, 7))
        self.undo_button = ttk.Button(action_row, text="Undo assistant edit", command=self.undo)
        self.undo_button.pack(side="left")
        self.example_box = ttk.Combobox(action_row, values=("Insert an example…", "Timeline guide / marker", "Split selected clip", "Shorten selected clip"), state="readonly", width=24)
        self.example_box.current(0)
        self.example_box.pack(side="right")
        self.example_box.bind("<<ComboboxSelected>>", self._example_selected)
        ttk.Label(command_bar, text="Voice fills this field only. Preview checks the command; Apply is always a separate click.", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        timeline_tab, result_tab, history_tab, help_tab = (ttk.Frame(self.tabs, padding=10) for _ in range(4))
        self.tabs.add(timeline_tab, text="Timeline")
        self.tabs.add(result_tab, text="Plan & result")
        self.tabs.add(history_tab, text="Action history")
        self.tabs.add(help_tab, text="Supported scope")
        self.timeline_tab, self.result_tab = timeline_tab, result_tab
        ttk.Label(timeline_tab, textvariable=self.selection_label, style="Muted.TLabel").pack(anchor="w", pady=(0, 7))
        tree_frame = ttk.Frame(timeline_tab)
        tree_frame.pack(fill="both", expand=True)
        self.clip_tree = ttk.Treeview(tree_frame, columns=("track", "start", "end", "duration", "id"), selectmode="browse")
        self.clip_tree.heading("#0", text="Sequence / track / clip")
        self.clip_tree.column("#0", width=255, minwidth=170)
        for key, title, width in (("track", "Track", 120), ("start", "Start frame", 88), ("end", "End (exclusive)", 110), ("duration", "Frames", 70), ("id", "Exact instance ID", 250)):
            self.clip_tree.heading(key, text=title)
            self.clip_tree.column(key, width=width, minwidth=60)
        vertical = ttk.Scrollbar(tree_frame, orient="vertical", command=self.clip_tree.yview)
        horizontal = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.clip_tree.xview)
        self.clip_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.clip_tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.clip_tree.bind("<<TreeviewSelect>>", self._selection_changed)
        timeline_footer = ttk.Frame(timeline_tab)
        timeline_footer.pack(before=tree_frame, side="bottom", fill="x", pady=(10, 0))
        self.export_button = ttk.Button(timeline_footer, text="Save inspection report", command=self.export_report)
        self.export_button.pack(side="left")
        self.open_output_button = ttk.Button(timeline_footer, text="Open current file in Kdenlive", command=self.open_output)
        self.open_output_button.pack(side="right")

        self.result_title = tk.StringVar(value="Inspect a project, then preview an explicit command.")
        ttk.Label(result_tab, textvariable=self.result_title, font=("Segoe UI Semibold", 12), wraplength=1050).pack(anchor="w", pady=(0, 8))
        self.result_text = self._text_panel(result_tab)
        self._replace_text(self.result_text, "Supported operations are shown in the Supported scope tab.\nNo project changes occur during inspection or preview.")
        self.history_tree = ttk.Treeview(history_tab, columns=("time", "operation", "status", "project"), show="headings", selectmode="browse")
        for key, title, width in (("time", "Recorded (UTC)", 180), ("operation", "Operation", 150), ("status", "Verification status", 145), ("project", "Project", 450)):
            self.history_tree.heading(key, text=title)
            self.history_tree.column(key, width=width, minwidth=70)
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind("<<TreeviewSelect>>", self._history_selected)
        self.history_records: dict[str, dict] = {}
        self.refresh_history_button = ttk.Button(history_tab, text="Refresh history", command=self.refresh_history)
        self.refresh_history_button.pack(before=self.history_tree, side="bottom", anchor="w", pady=(10, 0))
        help_text = self._text_panel(help_tab)
        self._replace_text(help_text, self._help_text())

        footer = ttk.Frame(outer)
        footer.pack(before=self.tabs, side="bottom", fill="x", pady=(12, 0))
        ttk.Label(footer, textvariable=self.status, style="Accent.TLabel", wraplength=1030).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=75)
        self.progress.pack(side="right")

    def _text_panel(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        widget = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, selectbackground="#255291", wrap="word", relief="flat", padx=13, pady=11, font=("Consolas", 10), highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        widget.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return widget

    @staticmethod
    def _replace_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    @staticmethod
    def _help_text():
        return """SUPPORTED IN THIS RELEASE

Kdenlive: inspect a saved .kdenlive project; add a timeline guide;
split or shorten the end of a simple, ungrouped clip without effects.
Trimming preserves later clip positions by adding a gap; it never ripples.
Projects with linked clips, effects, retiming, nested sequences, transitions,
or unknown metadata are rejected for clip edits. Document version 1.1 is
required for editing. Inspection can show other readable versions.

Every Kdenlive edit creates a new project file. The original is retained.
The companion observes saved files only, so save your editor changes first.
Reopen the resulting copy in Kdenlive and check playback and media paths.
XML validation is structural verification; editor reopening/rendering is
not certified by this application. Undo selects the unchanged prior saved
file in this companion and retains both copies; reopen it in the editor.

DaVinci Resolve: inspect the active project/timeline and add assistant-owned
timeline markers. Marker frames are zero-based offsets from timeline start,
not absolute timecode frames. Existing markers are never overwritten.
Undo removes an assistant marker only if its ownership and values still
match. Save the Resolve project normally to persist your changes.
External scripting availability depends on your installed Resolve edition
and settings. The included in-editor script is an alternative connection.

COMMAND EXAMPLES
  inspect
  list clips
  add guide at frame 10 named "Review point"
  add marker at frame 20 named "Check transition" color Green
  split clip selected at frame 25
  trim clip selected end by 5 frames
  undo
  stop

Select one clip row in this companion for "selected" commands. This is
separate from the editor's current selection. Names retain their case.
Only explicit supported English commands are accepted. No LLM, grading,
shot matching, export/render control, Microsoft 365 connection, or arbitrary
mouse/keyboard automation is enabled. Optional Windows offline dictation
fills the command field only; it never previews or applies an edit.

STOP AND RECOVERY
Stop revokes queued/running operations and cancels dictation. The local
shortcut is Ctrl+Shift+Space; the global shortcut works when Windows permits
registration. A host request already dispatched can still complete. Any
uncertain outcome is journaled as unknown; inspect before retrying. Unresolved
edits block further mutations to that project. No automatic replay occurs.
"""

    def _set_scope(self):
        if self.controller.editor == "kdenlive":
            self.scope_label.set("Saved project only · New copies for edits · Guides, simple split and end trim · Reopen every result in Kdenlive")
            self.project_label.set(str(self.controller.path) if self.controller.path else "Open a saved .kdenlive project, or use the demo")
        else:
            self.scope_label.set("Active Resolve timeline · Inspection and timeline markers · Marker frames are offsets from timeline start · Save in Resolve")
            identity = (self._snapshot or {}).get("identity", {})
            self.project_label.set(f"{identity.get('project_name', 'Resolve')} / {identity.get('timeline_name', 'Open a project and timeline, then Inspect')}")

    def _command_changed(self, *args):
        if self._preview_text is not None and self.command.get() != self._preview_text:
            self.controller.preview = None
            self._preview_text = None
        self._update_buttons()

    def _update_buttons(self):
        enabled = not self._busy and not self._closing
        for widget in (self.inspect_button, self.preview_button, self.undo_button, self.refresh_history_button):
            widget.configure(state="normal" if enabled else "disabled")
        self.editor_box.configure(state="readonly" if enabled else "disabled")
        self.example_box.configure(state="readonly" if enabled else "disabled")
        self.tools_button.configure(state="normal" if enabled else "disabled")
        self.open_button.configure(state="normal" if enabled and self.controller.editor == "kdenlive" else "disabled")
        self.demo_button.configure(state="normal" if enabled and self.controller.editor == "kdenlive" else "disabled")
        self.export_button.configure(state="normal" if enabled and self._snapshot is not None else "disabled")
        self.dictate_button.configure(state="normal" if enabled and self._voice_available else "disabled")
        self.open_output_button.configure(state="normal" if enabled and self.controller.editor == "kdenlive" and self.controller.path is not None else "disabled")
        preview = self.controller.preview
        valid_preview = enabled and preview is not None and self._preview_text == self.command.get()
        if valid_preview:
            valid_preview = preview.get("generation") == self.controller.supervisor.generation
        self.apply_button.configure(state="normal" if valid_preview else "disabled")

    def _submit(self, kind: str, task: Callable, *, lease=None):
        if self._closing or self._busy:
            return False
        lease = lease or self.controller.supervisor.capture()
        self._busy = True
        self.status.set({"inspect": "Inspecting saved project…", "preview": "Checking command and project state…", "apply": "Applying the reviewed plan…", "undo": "Checking and undoing the assistant edit…", "dictate": "Listening locally… Stop cancels dictation.", "report": "Saving the inspection report…", "history": "Reading action history…", "voice_probe": "Checking optional Windows dictation…"}.get(kind, "Working…"))
        self.progress.start(12)
        self._update_buttons()

        def worker():
            try:
                lease.assert_active()
                result = task(lease)
                records = self.controller.history.list_recent(100)
                self.messages.put(("success", kind, result, lease.generation, records))
            except Exception as exc:
                self.messages.put(("error", kind, str(exc), lease.generation, None))
            finally:
                if self._closing:
                    self._close_controller()
                self.messages.put(("done", kind, None, lease.generation, None))

        self._active_thread = threading.Thread(target=worker, name="EditingCopilot-" + kind, daemon=True)
        self._active_thread.start()
        return True

    def _poll(self):
        if self._closing:
            return
        while True:
            try:
                state, kind, result, generation, records = self.messages.get_nowait()
            except queue.Empty:
                break
            if state == "done":
                self._busy = False
                self.progress.stop()
                self._active_thread = None
                self._update_buttons()
                if not self._voice_checked:
                    self._schedule(10, self._probe_voice)
            elif state == "stopped":
                self._show_stopped()
            elif state == "voice":
                self._handle_voice(kind, result)
            elif state == "error":
                self.status.set("Operation did not complete. Review the message before continuing.")
                self._show_result("No success claimed", {"message": result})
                if kind == "voice_probe":
                    self._voice_checked = True
                    self._voice_available = False
            elif state == "success":
                if records is not None:
                    self._show_history(records)
                revoked = generation != self.controller.supervisor.generation
                if revoked and kind not in ("apply", "undo", "report"):
                    self.status.set("Stopped. Discarded the interrupted inspection or preview.")
                    continue
                self._success(kind, result, revoked)
        self._schedule(40, self._poll)

    def _success(self, kind, result, revoked=False):
        if kind == "voice_probe":
            self._voice_checked = True
            self._voice_available, self._voice_reason = result
            self.status.set("Ready · " + ("Local dictation available" if self._voice_available else "Typed commands available"))
            self._update_buttons()
            return
        if kind == "dictate":
            self.command.set(result)
            self.command_entry.focus_set()
            self.status.set("Dictation inserted. Review the text, then click Preview.")
            return
        if kind == "inspect":
            self._show_snapshot(result)
            self._show_result("Read-only inspection", result, select=False)
            self.status.set("Inspection complete. Select a timeline row or enter an explicit command.")
        elif kind == "preview":
            snapshot = result.get("snapshot") or self.controller.snapshot
            if snapshot is not None:
                self._show_snapshot(snapshot)
            if result.get("operation") == "undo":
                self._show_result("Undo requires the Undo assistant edit button", result)
                self.status.set("Use Undo assistant edit to verify and reverse the last matching edit.")
            else:
                if self.controller.preview is not None:
                    self._preview_text = self.controller.preview.get("text")
                self._show_result(result.get("summary", "Reviewed command"), result)
                self.status.set("Preview ready. Review the plan, then click Apply." if self.controller.preview is not None else "Read-only command complete.")
        elif kind == "apply":
            if result.get("output"):
                self._last_output = Path(result["output"])
            self._preview_text = None
            self._snapshot = None
            self._clear_rows()
            self._set_scope()
            self._show_result("Project copy published — reopen verification required" if result.get("editor_reopen_verified") is False else "Editor change read back successfully", result)
            self.status.set("Result recorded. Open and check the copy in Kdenlive." if result.get("output") else "Marker verified. Save your project in Resolve.")
            if revoked:
                self.status.set("Stopped after dispatch. The recorded result may include a completed edit; review it before continuing.")
        elif kind == "undo":
            if self.controller.editor == "kdenlive" and result.get("path"):
                self._last_output = Path(result["path"])
            self._preview_text = None
            self._snapshot = None
            self._clear_rows()
            self._set_scope()
            self._show_result(result.get("summary", "Assistant edit undone and verified"), result)
            self.status.set("Undo complete. Reopen the selected previous file in Kdenlive." if self.controller.editor == "kdenlive" else "Assistant marker removed. Save your project in Resolve.")
        elif kind == "report":
            self._show_result("Inspection report saved", result)
            self.status.set("Inspection report saved. It describes the recorded snapshot time.")
        elif kind == "history":
            self.status.set("Action history refreshed.")
        elif kind == "install":
            self._show_result("Integration installed for your account", result)
            self.status.set(result.get("message", "Installation complete."))

    def _show_result(self, title, result, *, select=True):
        self.result_title.set(str(title))
        self._replace_text(self.result_text, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if select:
            self.tabs.select(self.result_tab)

    def _clear_rows(self):
        children = self.clip_tree.get_children()
        if children:
            self.clip_tree.delete(*children)
        self._row_ids.clear()
        self._row_data.clear()
        self.selection_label.set("No timeline clip selected")

    def _show_snapshot(self, snapshot):
        selected = self.selected_instance()
        self._snapshot = copy.deepcopy(snapshot)
        self._snapshot_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._clear_rows()
        if snapshot.get("editor") == "kdenlive":
            for sequence in snapshot.get("sequences", []):
                sequence_row = self.clip_tree.insert("", "end", text=sequence.get("name", sequence.get("id", "Sequence")), open=True)
                for track in sequence.get("tracks", []):
                    track_row = self.clip_tree.insert(sequence_row, "end", text=track.get("name", track.get("id", "Track")) + (" · locked" if track.get("locked") else ""), open=True)
                    for playlist in track.get("playlists", []):
                        playlist_row = self.clip_tree.insert(track_row, "end", text="Playlist " + str(playlist.get("id", "")), open=True)
                        for instance in playlist.get("instances", []):
                            self._insert_clip(playlist_row, instance, track.get("name", track.get("id", "")))
        else:
            grouped = {}
            for row in timeline_rows(snapshot):
                track_name = row["track_name"]
                if track_name not in grouped:
                    grouped[track_name] = self.clip_tree.insert("", "end", text=track_name, open=True)
                self._insert_clip(grouped[track_name], row, track_name)
        if selected is not None:
            restored = next((row for row, identifier in self._row_ids.items() if identifier == selected), None)
            if restored is not None:
                self.clip_tree.selection_set(restored)
                self.clip_tree.see(restored)
        self._set_scope()
        self._update_buttons()

    def _insert_clip(self, parent, instance, track_name):
        identifier = instance.get("instance_id")
        row = self.clip_tree.insert(parent, "end", text=instance.get("name", "Clip"), values=(track_name, instance.get("timeline_in", ""), instance.get("timeline_out_exclusive", ""), instance.get("duration_frames", ""), identifier or "unavailable"))
        self._row_ids[row] = identifier
        self._row_data[row] = instance

    def selected_instance(self):
        selection = self.clip_tree.selection()
        return self._row_ids.get(selection[0]) if selection else None

    def _selection_changed(self, event=None):
        selected = self.selected_instance()
        self.selection_label.set("Selected in companion: " + selected if selected else "Select one clip row for commands using selected")
        # A new selection must not change the target of an already reviewed plan.
        if self._preview_text is not None and "selected" in self._preview_text.casefold().split() and selected != self._selected_instance_at_preview:
            self.controller.preview = None
            self._preview_text = None
            self._update_buttons()

    def _show_history(self, records):
        children = self.history_tree.get_children()
        if children:
            self.history_tree.delete(*children)
        self.history_records = {record["id"]: record for record in records}
        for record in records:
            self.history_tree.insert("", "end", iid=record["id"], values=(record.get("created_at", "")[:19].replace("T", " "), record.get("operation"), record.get("status"), record.get("project_hash") or ""))

    def _history_selected(self, event=None):
        selection = self.history_tree.selection()
        if selection and selection[0] in self.history_records:
            record = self.history_records[selection[0]]
            self._show_result("Recorded action: " + record["status"], record)

    def _editor_changed(self, event=None):
        if self._busy:
            self.editor.set("Kdenlive" if self.controller.editor == "kdenlive" else "DaVinci Resolve")
            return
        editor = "kdenlive" if self.editor.get() == "Kdenlive" else "resolve"
        self.controller.select(editor)
        if getattr(self, "config", None) is not None and self.config["ui"]["editor"] != editor:
            self.config["ui"]["editor"] = editor
            try: save_config(self.controller.directory, self.config)
            except OSError: pass
        self._snapshot = None
        self._preview_text = None
        self._clear_rows()
        self._set_scope()
        self.command.set('add guide at frame 10 named "Review point"' if editor == "kdenlive" else 'add marker at frame 10 named "Review point" color Green')
        self.status.set("Open a saved Kdenlive project." if editor == "kdenlive" else "Open a Resolve project and timeline, then click Inspect.")
        self._update_buttons()

    def open_project(self):
        if self._busy or self._closing:
            return
        path = filedialog.askopenfilename(parent=self.root, title="Open a saved Kdenlive project", filetypes=(("Kdenlive project", "*.kdenlive"),))
        if path:
            self.controller.select("kdenlive", path)
            self.editor.set("Kdenlive")
            self._snapshot = None
            self._preview_text = None
            self._set_scope()
            self.inspect_project()

    def _startup_demo(self):
        if self._busy or self._closing:
            return
        source = self.resource_dir / "demo.kdenlive"
        if not source.is_file():
            self.status.set("Demo resource unavailable. Open a saved Kdenlive project.")
            self._probe_voice()
            return
        try:
            folder = self.controller.directory / "examples"
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / "Demo.kdenlive"
            if not destination.exists():
                shutil.copyfile(source, destination)
            self.controller.select("kdenlive", destination)
            self.editor.set("Kdenlive")
            self._preview_text = None
            self._set_scope()
            self.inspect_project()
        except OSError as exc:
            self._show_result("Demo could not be opened", {"message": str(exc)})
            self._probe_voice()

    def inspect_project(self):
        self._submit("inspect", lambda lease: self.controller.inspect(lease))

    def preview_command(self):
        if self._busy or self._closing:
            return
        text = self.command.get().strip()
        if text.casefold() == "stop":
            self.stop()
            return
        if text.casefold() == "export report":
            self.export_report()
            return
        selected = self.selected_instance()
        self._selected_instance_at_preview = selected
        self.controller.preview = None
        self._preview_text = None
        self._submit("preview", lambda lease: self.controller.plan(text, selected_instance=selected, lease=lease))

    def apply_preview(self):
        if self._busy or self._closing or self.controller.preview is None:
            return
        if self._preview_text != self.command.get():
            self.status.set("The command changed. Generate a fresh preview.")
            return
        expected_text, selected = self.command.get(), self.selected_instance()
        self._submit("apply", lambda lease: self.controller.apply(lease, expected_text=expected_text, selected_instance=selected))

    def undo(self):
        self._submit("undo", lambda lease: self.controller.undo(lease))

    def refresh_history(self):
        self._submit("history", lambda lease: {"records": self.controller.history.list_recent(100)})

    def _example_selected(self, event=None):
        index = self.example_box.current()
        self.example_box.current(0)
        if index == 1:
            self.command.set('add guide at frame 10 named "Review point"' if self.controller.editor == "kdenlive" else 'add marker at frame 10 named "Review point" color Green')
        elif index in (2, 3):
            if self.controller.editor != "kdenlive":
                self.status.set("Resolve clip edits are not supported. Use a marker command.")
                return
            if not self.selected_instance():
                self.status.set("Select a clip row in the Timeline tab first.")
                self.tabs.select(self.timeline_tab)
                return
            selection = self.clip_tree.selection()[0]
            row = self._row_data[selection]
            midpoint = row["timeline_in"] + max(1, row["duration_frames"] // 2)
            self.command.set(f"split clip selected at frame {midpoint}" if index == 2 else "trim clip selected end by 1 frame")
        self.command_entry.focus_set()

    def export_report(self):
        if self._busy or self._closing:
            return
        if self._snapshot is None:
            self.status.set("Inspect the project before saving a report.")
            return
        name = filedialog.asksaveasfilename(parent=self.root, title="Save the recorded inspection as JSON", defaultextension=".json", initialfile="Editing-Copilot-Inspection.json", filetypes=(("JSON inspection report", "*.json"),))
        if not name:
            return
        report = {"report_type": "editing-copilot-inspection", "snapshot_taken_at_utc": self._snapshot_time, "scope": "Recorded read-only snapshot; subsequent and unsaved editor changes are not included.", "inspection": copy.deepcopy(self._snapshot)}
        destination = Path(name)
        protected_paths = [self.controller.path] if self.controller.path is not None else []
        if self._snapshot.get("path"):
            protected_paths.append(Path(self._snapshot["path"]))
        project_folder = Path(self._snapshot.get("path") or destination).parent
        for asset in self._snapshot.get("assets", []):
            resource = asset.get("resource")
            if isinstance(resource, str) and resource and not resource.startswith("#"):
                asset_path = Path(resource)
                protected_paths.append(asset_path if asset_path.is_absolute() else project_folder / asset_path)
        try:
            validate_report_destination(destination, protected_paths)
        except (ValueError, OSError) as exc:
            self.status.set("Report was not saved. Choose a separate .json file.")
            self._show_result("Report destination rejected", {"message": str(exc)})
            return
        serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)

        def save(lease):
            lease.assert_active()
            save_report_atomic(destination, serialized, lease, protected_paths)
            return {"path": str(destination), "snapshot_taken_at_utc": self._snapshot_time}
        self._submit("report", save)

    def open_output(self):
        if self._busy or self._closing or self.controller.editor != "kdenlive" or self.controller.path is None:
            return
        target = Path(self.controller.path)
        executable = find_kdenlive_executable()
        if executable is None:
            messagebox.showinfo("Open the project in Kdenlive", "An installed Kdenlive executable was not found in its standard locations.\n\nOpen this file from Kdenlive:\n" + str(target), parent=self.root)
            return
        if target.suffix.casefold() != ".kdenlive" or not target.is_file():
            self.status.set("The selected project file is no longer available.")
            return
        try:
            subprocess.Popen([str(executable), str(target)], shell=False)
            self.status.set("Kdenlive was asked to open the selected file. Check media, playback, and guides in the editor.")
        except OSError as exc:
            self._show_result("Kdenlive could not open the project", {"message": str(exc), "path": str(target)})

    def _probe_voice(self):
        if not self._voice_checked and not self._busy and not self._closing:
            self._submit("voice_probe", lambda lease: voice_available())

    def _install_action(self, integration):
        if self._busy or self._closing:
            return
        from .install import install_companion, install_resolve_menu
        installer = install_resolve_menu if integration == "resolve" else install_companion

        def install(lease):
            lease.assert_active()
            return installer(self.resource_dir)
        self._submit("install", install)

    def dictate(self):
        if self._busy or self._closing or not self._voice_available:
            return
        self._voice_cancel = threading.Event()
        cancel = self._voice_cancel

        def listen(lease):
            recognized, errors = [], []
            dictate_once(recognized.append, errors.append, cancel)
            lease.assert_active()
            if errors:
                raise RuntimeError(errors[0])
            if not recognized:
                raise RuntimeError("No speech recognized. Type a command or try again.")
            return recognized[0]
        self._submit("dictate", listen)

    def _hotkey_stop(self):
        # Windows delivers this on its hotkey thread. Do not call any Tk method.
        if self._executor is not None:
            self._executor.stop_event.set()
        self.controller.stop()
        self._voice_cancel.set()
        self.messages.put(("stopped", "stop", None, None, None))

    # ------------------------------------------------------------ hands-free voice
    def _mode_changed(self, event=None):
        reverse = {v: k for k, v in MODE_LABELS.items()}
        self.config["mode"] = reverse.get(self.mode.get(), "auto")
        try:
            save_config(self.controller.directory, self.config)
        except OSError as exc:
            log.warning("could not save config: %s", exc)
        if self._listener is not None:
            self.toggle_handsfree(); self.toggle_handsfree()  # restart with the new mode
        self.status.set("Voice/AI mode: " + self.mode.get())

    def toggle_handsfree(self):
        if self._listener is not None:
            self._listener.stop(); self._listener = None
            self.voice_state.set("Hands-free: off")
            self._overlay_set(listening="○ Not listening")
            self.handsfree_button.configure(text="Hands-free voice")
            return
        try:
            recognizer = voice_mod.build_recognizer(self.config, self.controller.directory)
        except voice_mod.VoiceError as exc:
            self.voice_state.set("Hands-free unavailable: " + str(exc))
            return
        v = self.config["voice"]
        self._listener = voice_mod.VoiceListener(recognizer, self._on_voice_text,
                                                 lambda msg: self.messages.put(("voice", "error", msg, None, None)),
                                                 rate=v["sample_rate"], device=v["device"], max_s=v["utterance_timeout_s"]).start()
        wake = v["wake_word"] if v["require_wake_word"] and v["wake_word"] else ""
        self.voice_state.set(f"Hands-free: listening ({recognizer.name})" + (f" · say \"{wake} …\"" if wake else ""))
        self._overlay_set(listening="● Listening · " + recognizer.name + (f" · say “{wake} …”" if wake else ""))
        self.speaker.say("Listening.", "listen")
        self.handsfree_button.configure(text="Stop listening")

    def _fps(self):
        try:
            return float((self._snapshot or {}).get("fps") or (self._snapshot or {}).get("profile", {}).get("fps") or 25.0)
        except (TypeError, ValueError, AttributeError):
            return 25.0

    def _on_voice_text(self, text):
        # Listener thread: no Tk calls here.
        v = self.config["voice"]
        body = strip_wake_word(text, v["wake_word"], v["require_wake_word"])
        if body is None or not body:
            return
        try:
            intent = understand(body, self.config, self._fps(), self.controller.editor)
        except Exception as exc:
            log.exception("voice understanding failed")
            self.messages.put(("voice", "error", str(exc), None, None)); return
        self.messages.put(("voice", "intent", intent, None, None))

    # ------------------------------------------------------------ UI automation, macros, knowledge
    def executor(self):
        if self._executor is None:
            from .uiauto import WindowsBackend
            self._executor = Executor(WindowsBackend(), self.config, self.macros)
        return self._executor

    def knowledge(self):
        if self._kb is None:
            self._kb = KnowledgeBase(self.resource_dir / "knowledge" / "kdenlive_grading_master_reference.md")
        return self._kb

    def _background(self, label, fn):
        def run():
            try:
                result = fn()
                self.messages.put(("voice", "result", (label, result), None, None))
            except (ActionError, LiveControlError, RuntimeError, OSError) as exc:
                log.warning("%s failed: %s", label, exc)
                self.messages.put(("voice", "error", str(exc), None, None))
        threading.Thread(target=run, name="EditingCopilot-ui", daemon=True).start()

    def run_ui_actions(self, actions, description=None):
        editor = self.controller.editor
        self._background("UI action", lambda: self.executor().request(editor, actions, description))

    def list_editor_controls(self):
        editor = self.controller.editor
        self._background("Controls", lambda: {"summary": "Visible controls (UI Automation)", "controls": self.executor().list_controls(editor)})

    def open_macro_editor(self):
        editor = self.controller.editor
        win = tk.Toplevel(self.root); win.title(f"Voice macros · {editor}"); win.configure(bg=BG); win.geometry("760x520")
        names = tk.Listbox(win, width=26, bg=PANEL, fg=TEXT); names.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(win); right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        name_var = tk.StringVar()
        ttk.Label(right, text="Name (say: “run macro <name>” or just the name)").pack(anchor="w")
        ttk.Entry(right, textvariable=name_var).pack(fill="x")
        ttk.Label(right, text='Steps (JSON list), e.g. [{"kind":"click","label":"File","role":"menu"}, {"kind":"wait","seconds":0.5}, {"kind":"key","text":"ctrl+s"}, {"kind":"drag","label":"Intro","to_label":"V2"}]',
                  style="Muted.TLabel", wraplength=480).pack(anchor="w", pady=(8, 2))
        steps = tk.Text(right, height=16, bg="#243246", fg=TEXT, insertbackground=TEXT); steps.pack(fill="both", expand=True)
        msg = tk.StringVar(); ttk.Label(right, textvariable=msg, style="Accent.TLabel", wraplength=480).pack(anchor="w")

        def refresh():
            names.delete(0, "end")
            for n in self.macros.data.get(editor, {}):
                names.insert("end", n)
            msg.set("; ".join(self.macros.errors))

        def pick(event=None):
            sel = names.curselection()
            if sel:
                n = names.get(sel[0]); name_var.set(n)
                steps.delete("1.0", "end"); steps.insert("1.0", json.dumps(self.macros.data[editor][n], indent=1))

        def save():
            try:
                acts = [Action.from_dict(d) for d in json.loads(steps.get("1.0", "end") or "[]")]
                self.macros.put(editor, name_var.get(), acts); msg.set("Saved."); refresh()
            except (ValueError, ActionError, LiveControlError, TypeError) as exc:
                msg.set(f"Not saved: {exc}")

        def delete():
            if name_var.get() and messagebox.askyesno("Delete macro", f"Delete macro “{name_var.get()}”?", parent=win):
                self.macros.delete(editor, name_var.get()); refresh()
        names.bind("<<ListboxSelect>>", pick)
        row = ttk.Frame(right); row.pack(fill="x", pady=6)
        ttk.Button(row, text="Save", style="Primary.TButton", command=save).pack(side="left")
        ttk.Button(row, text="Delete", command=delete).pack(side="left", padx=6)
        ttk.Button(row, text="Reload file", command=lambda: (self.macros.load(), refresh())).pack(side="left")
        refresh()

    # ------------------------------------------------------------ overlay, cheat sheet, wizard
    def _overlay_set(self, heard=None, result=None, listening=None):
        if self._overlay is None:
            return
        try:
            if listening is not None:
                self._ov_state.set(listening)
            if heard is not None:
                self._ov_heard.set("Heard: " + heard)
            if result is not None:
                self._ov_result.set(result[:160])
        except tk.TclError:
            self._overlay = None

    def toggle_overlay(self, show=None):
        if self._overlay is not None and show is not True:
            try: self._overlay.destroy()
            except tk.TclError: pass
            self._overlay = None; return
        if self._overlay is not None:
            return
        ov = tk.Toplevel(self.root); ov.overrideredirect(True); ov.attributes("-topmost", True)
        try: ov.attributes("-alpha", 0.9)
        except tk.TclError: pass
        ov.configure(bg="#0b1220")
        w, h = 430, 92
        ov.geometry(f"{w}x{h}+{self.root.winfo_screenwidth() - w - 24}+{self.root.winfo_screenheight() - h - 70}")
        self._ov_state, self._ov_heard, self._ov_result = tk.StringVar(value=self.voice_state.get()), tk.StringVar(value="Heard: —"), tk.StringVar(value="")
        for var, color, font in ((self._ov_state, ACCENT, ("Segoe UI Semibold", 10)), (self._ov_heard, TEXT, ("Segoe UI", 10)), (self._ov_result, MUTED, ("Segoe UI", 9))):
            tk.Label(ov, textvariable=var, bg="#0b1220", fg=color, font=font, anchor="w", wraplength=w - 16, justify="left").pack(fill="x", padx=8, pady=1)
        ov.bind("<Button-1>", lambda e: (self.root.deiconify(), self.root.lift()))
        ov.bind("<Button-3>", lambda e: self.toggle_overlay(False))
        self._overlay = ov

    def open_cheatsheet(self):
        win = tk.Toplevel(self.root); win.title("What can I say?"); win.configure(bg=BG); win.geometry("980x560")
        text = tk.Text(win, bg=PANEL, fg=TEXT, font=("Consolas", 10), wrap="word", padx=12, pady=10)
        text.insert("1.0", CHEATSHEET + "\nYour macros: " + (", ".join(self.macros.names(self.controller.editor)) or "none yet"))
        text.configure(state="disabled"); text.pack(fill="both", expand=True)

    def _first_run(self):
        try:
            if self.config["ui"]["editor"] == "resolve" and self.controller.editor != "resolve":
                self.editor.set("DaVinci Resolve"); self._editor_changed()
            if self.config["ui"]["overlay"]:
                self.toggle_overlay(True)
            if not self.config["ui"]["first_run_done"]:
                self.open_wizard()
            elif self.config["ui"]["listen_on_start"] and self._listener is None:
                self.toggle_handsfree()
        except Exception:
            log.exception("first-run setup failed")

    def open_wizard(self):
        from .wizard import SetupWizard
        SetupWizard(self)

    def apply_settings(self, editor=None, mode=None, feedback=None, startup=None, keys=None, overlay=None):
        cfg = self.config
        if editor:
            cfg["ui"]["editor"] = editor
            self.editor.set("Kdenlive" if editor == "kdenlive" else "DaVinci Resolve"); self._editor_changed()
        if mode:
            cfg["mode"] = mode; self.mode.set(MODE_LABELS[mode])
        if feedback:
            cfg["ui"]["feedback"] = feedback; self.speaker.mode = feedback
        if startup is not None:
            try:
                cfg["ui"]["start_with_windows"] = set_start_with_windows(startup)
            except Exception as exc:
                log.warning("start-with-Windows failed: %s", exc)
        if overlay is not None:
            cfg["ui"]["overlay"] = overlay; self.toggle_overlay(overlay) if overlay else (self._overlay and self.toggle_overlay(False))
        for env_name, value in (keys or {}).items():
            if value is not None:
                set_user_env(env_name, value.strip())
        cfg["ui"]["first_run_done"] = True
        save_config(self.controller.directory, cfg)
        if self._listener is not None:
            self.toggle_handsfree(); self.toggle_handsfree()

    def _handle_voice(self, kind, payload):
        if kind == "error":
            self.voice_state.set("Voice: " + str(payload))
            self._overlay_set(result=str(payload)); self.speaker.say(str(payload), "error"); return
        if kind == "result":
            label, result = payload
            summary = result.get('summary', '')
            self.voice_state.set(f"{label}: {summary}")
            self._overlay_set(result=f"{label}: {summary}")
            outcome = result.get("outcome", "")
            self.speaker.say("Please confirm." if outcome == "needs_confirmation" else ("Stopped." if outcome == "cancelled" else "Done."),
                             "confirm" if outcome == "needs_confirmation" else "ok")
            self._show_result(label, result, select=False)
            return
        if kind == "intent":
            self._overlay_set(heard=payload.source)
        intent = payload
        self.voice_state.set(f"Heard: “{intent.source}”")
        log.info("voice intent %s %r", intent.kind, intent.value)
        if intent.kind == "control":
            action = intent.value
            if action == "stop":
                self.stop()
            elif action == "confirm" and self._executor is not None and self._executor.pending:
                self._background("Confirmed action", self._executor.confirm)
            elif action == "cancel" and self._executor is not None and self._executor.cancel():
                self.voice_state.set("Cancelled. Nothing was clicked.")
            elif self._busy:
                self.status.set("Busy - say “stop” to interrupt.")
            elif action == "preview":
                self.preview_command()
            elif action in ("apply", "confirm"):
                if not self.config["voice"]["allow_voice_apply"]:
                    self.status.set("Voice Apply is disabled in config; click Apply preview.")
                elif str(self.apply_button.cget("state")) == "normal":
                    self.apply_preview()
                else:
                    self.status.set("Nothing to apply: preview a command first.")
            elif action == "cancel":
                self.controller.preview = None; self._preview_text = None
                self._update_buttons(); self.status.set("Preview cancelled. No change made.")
            elif action == "undo":
                self.undo()
            elif action == "inspect":
                self.inspect_project()
        elif intent.kind == "command":
            self.command.set(intent.value)
            if self.config["voice"]["auto_preview"] and not self._busy:
                self.preview_command()
                self.status.set("Preview ready. Say “apply” to confirm or “cancel”.")
        elif intent.kind == "live":
            self.run_ui_actions([Action("live", text=intent.value)])
        elif intent.kind == "ui":
            self.run_ui_actions(intent.data)
        elif intent.kind == "workflow":
            actions, destructive = intent.data
            editor = self.controller.editor
            self._background("Workflow", lambda: self.executor().request(editor, actions, intent.value, confirm=destructive))
        elif intent.kind == "macro":
            verb, name = intent.data
            editor = self.controller.editor
            try:
                if verb == "record":
                    self.voice_state.set(self.executor().start_recording(editor, name))
                elif verb == "stop_recording":
                    self.voice_state.set(self.executor().stop_recording())
                elif verb == "list":
                    self.voice_state.set("Macros: " + (", ".join(self.macros.names(editor)) or "none"))
                else:
                    self._background("Macro", lambda: self.executor().run_macro(editor, name))
            except (ActionError, RuntimeError) as exc:
                self.voice_state.set(str(exc))
        elif intent.kind == "help":
            from .assistant import llm_chain
            chain = llm_chain(self.config)
            ask = chain[0][1] if chain else None
            self._background("Reference", lambda: self.knowledge().answer(intent.data, self.config, ask))
        elif MacroStore.key(intent.source) in self.macros.names(self.controller.editor):
            editor = self.controller.editor
            self._background("Macro", lambda: self.executor().run_macro(editor, intent.source))
        else:
            self.voice_state.set(f"Not understood: “{intent.source}”. Say e.g. “copilot add marker at 10 seconds named Intro”.")

    def _show_stopped(self):
        self._preview_text = None
        self.status.set("Stopped. A dispatched editor change can still finish; inspect its recorded outcome.")
        self._update_buttons()

    def stop(self):
        if self._executor is not None:
            self._executor.stop_event.set(); self._executor.cancel()
        self.controller.stop()
        self._voice_cancel.set()
        self._show_stopped()

    def _close_controller(self):
        if not self._closed_controller:
            self._closed_controller = True
            self.controller.close()

    def close(self):
        if self._closing:
            return
        self._closing = True
        for token in list(self._after_ids):
            try:
                self.root.after_cancel(token)
            except tk.TclError:
                pass
        self._after_ids.clear()
        self._close_started = time.monotonic()
        self.controller.stop()
        self._voice_cancel.set()
        if self._listener is not None:
            self._listener.stop()
        if self._hotkey is not None:
            self._hotkey.close()
        self.status.set("Stopping pending work and closing…")
        self._update_buttons()
        self._wait_for_close()

    def _wait_for_close(self):
        active = self._active_thread is not None and self._active_thread.is_alive()
        if not active:
            self._close_controller()
            self.root.destroy()
        elif time.monotonic() - self._close_started < 5:
            self._schedule(40, self._wait_for_close)
        else:
            # The worker owns deferred cleanup. Never close SQLite underneath it.
            # A frozen process exit releases handles; startup recovery handles
            # any dispatched operation that did not reach verification.
            self.root.destroy()


def run_ui(controller: Controller | None = None, resource_dir: Path | str | None = None, minimized: bool = False):
    root = tk.Tk()
    if minimized:
        root.iconify()
    try:
        controller = controller or Controller()
        app = CopilotApp(root, controller, resource_dir)
        root.mainloop()
        return app
    except Exception:
        if controller is not None:
            controller.close()
        try:
            root.destroy()
        except tk.TclError:
            pass
        raise
