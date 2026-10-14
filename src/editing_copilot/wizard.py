"""First-run setup wizard: editor, voice/AI mode, microphone test, optional free API key, feedback, startup."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk

from . import voice as voice_mod

BG, PANEL, TEXT, MUTED, ACCENT = "#111827", "#182235", "#e6edf7", "#a6b5c9", "#93c5fd"


def record_seconds(seconds: float, rate: int = 16000, device=None) -> bytes:
    import sounddevice as sd
    data = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16", device=device)
    sd.wait()
    return data.tobytes()


class SetupWizard:
    def __init__(self, app):
        self.app, cfg = app, app.config
        self.win = win = tk.Toplevel(app.root)
        win.title("Editing Copilot · Setup"); win.configure(bg=BG); win.geometry("640x620"); win.transient(app.root)
        f = ttk.Frame(win, padding=18); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Welcome to Editing Copilot", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="Four quick choices. You can change them later in Tools › Setup wizard.", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))

        self.editor = tk.StringVar(value=cfg["ui"]["editor"])
        self._section(f, "1. Which editor do you use most?")
        row = ttk.Frame(f); row.pack(anchor="w")
        for val, label in (("kdenlive", "Kdenlive"), ("resolve", "DaVinci Resolve")):
            ttk.Radiobutton(row, text=label, value=val, variable=self.editor).pack(side="left", padx=(0, 16))

        self.mode = tk.StringVar(value=cfg["mode"])
        self._section(f, "2. Voice & AI (all free)")
        for val, label in (("auto", "Auto – online if a key is set, otherwise offline (recommended)"),
                           ("local", "Offline on this PC only (private, no key needed)"),
                           ("online", "Online free tier (Groq or Gemini key needed)")):
            ttk.Radiobutton(f, text=label, value=val, variable=self.mode).pack(anchor="w")
        keyrow = ttk.Frame(f); keyrow.pack(fill="x", pady=(6, 0))
        self.provider = tk.StringVar(value=cfg["online"]["provider"])
        ttk.Combobox(keyrow, textvariable=self.provider, values=("groq", "gemini"), state="readonly", width=8).pack(side="left")
        self.key = tk.StringVar()
        ttk.Entry(keyrow, textvariable=self.key, show="•").pack(side="left", fill="x", expand=True, padx=6)
        env = cfg["online"][f"{self.provider.get()}_api_key_env"]
        ttk.Label(f, text=("A key is already saved. " if os.environ.get(env) else "") +
                  "Optional. Free keys: console.groq.com/keys or aistudio.google.com/apikey. Saved as a Windows user variable, never in a file.",
                  style="Muted.TLabel", wraplength=590).pack(anchor="w")

        self._section(f, "3. Microphone test")
        mic = ttk.Frame(f); mic.pack(fill="x")
        self.mic_result = tk.StringVar(value="Press Test and say: “copilot play”.")
        self.test_btn = ttk.Button(mic, text="Test (3 s)", command=self.test_mic); self.test_btn.pack(side="left")
        ttk.Label(mic, textvariable=self.mic_result, style="Accent.TLabel", wraplength=470).pack(side="left", padx=8)

        self._section(f, "4. Feedback and start-up")
        self.feedback = tk.StringVar(value=cfg["ui"]["feedback"])
        row = ttk.Frame(f); row.pack(anchor="w")
        for val, label in (("beep", "Beeps"), ("speech", "Spoken replies"), ("off", "Silent")):
            ttk.Radiobutton(row, text=label, value=val, variable=self.feedback).pack(side="left", padx=(0, 14))
        self.startup = tk.BooleanVar(value=cfg["ui"]["start_with_windows"])
        self.overlay = tk.BooleanVar(value=cfg["ui"]["overlay"])
        self.listen = tk.BooleanVar(value=cfg["ui"]["listen_on_start"])
        ttk.Checkbutton(f, text="Start with Windows", variable=self.startup).pack(anchor="w")
        ttk.Checkbutton(f, text="Show the small status overlay (listening / heard / result)", variable=self.overlay).pack(anchor="w")
        ttk.Checkbutton(f, text="Start listening automatically", variable=self.listen).pack(anchor="w")
        bar = ttk.Frame(f); bar.pack(fill="x", side="bottom", pady=(12, 0))
        ttk.Button(bar, text="Finish", style="Primary.TButton", command=self.finish).pack(side="right")
        ttk.Button(bar, text="What can I say?", command=app.open_cheatsheet).pack(side="left")

    def _section(self, parent, text):
        ttk.Label(parent, text=text, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(12, 3))

    def test_mic(self):
        self.test_btn.configure(state="disabled"); self.mic_result.set("Listening… speak now.")
        cfg = dict(self.app.config); cfg["mode"] = self.mode.get()
        cfg["online"] = dict(cfg["online"], provider=self.provider.get())
        if self.key.get().strip():
            os.environ[cfg["online"][f"{self.provider.get()}_api_key_env"]] = self.key.get().strip()

        def run():
            try:
                pcm = record_seconds(3.0, cfg["voice"]["sample_rate"], cfg["voice"]["device"])
                level = voice_mod.rms(pcm)
                if level < 120:
                    msg = "Very quiet – check Windows microphone privacy settings and the input device."
                else:
                    rec = voice_mod.build_recognizer(cfg, self.app.controller.directory)
                    text = rec.transcribe(pcm)
                    msg = f"Heard: “{text}” ({rec.name}, level {int(level)})" if text else f"Sound OK (level {int(level)}) but no words recognised – speak closer."
            except Exception as exc:
                msg = f"Microphone test failed: {exc}"
            self.win.after(0, lambda: (self.mic_result.set(msg), self.test_btn.configure(state="normal")))
        threading.Thread(target=run, daemon=True).start()

    def finish(self):
        cfg = self.app.config
        cfg["online"]["provider"] = self.provider.get()
        cfg["ui"]["listen_on_start"] = self.listen.get()
        keys = {}
        if self.key.get().strip():
            keys[cfg["online"][f"{self.provider.get()}_api_key_env"]] = self.key.get().strip()
        self.app.apply_settings(editor=self.editor.get(), mode=self.mode.get(), feedback=self.feedback.get(),
                                startup=self.startup.get(), keys=keys, overlay=self.overlay.get())
        self.win.destroy()
        if self.listen.get() and self.app._listener is None:
            self.app.toggle_handsfree()
