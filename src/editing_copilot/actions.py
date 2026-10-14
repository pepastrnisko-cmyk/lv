"""Voice-driven UI actions and macros with safety rules.

Action kinds: click (label, role, button, double), click_at (x, y, button, double),
key (spec), type (text), scroll (notches), wait (seconds), live (editor shortcut action).

Safety (applies to single actions and every macro step):
 * the target editor window must be in front (we try to focus it once);
 * destructive targets/keys (delete, quit, overwrite, render, project settings, ...)
   need a spoken "confirm" first - macros containing one are confirmed up front;
 * a shared stop event (Stop button / Esc / Ctrl+Shift+Space / "stop") aborts between steps;
 * every action is logged.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

from . import live
from .uiauto import normalize_label, rank

log = logging.getLogger(__name__)

DESTRUCTIVE_WORDS = ("delete", "remove", "quit", "exit", "close project", "overwrite", "replace", "discard",
                     "don't save", "dont save", "erase", "clear", "reset", "render", "project settings",
                     "trash", "purge", "format", "revert", "extract", "lift", "ripple delete")
DESTRUCTIVE_KEYS = ("delete", "shift+delete", "ctrl+q", "alt+f4", "ctrl+return", "ctrl+w")
KINDS = ("click", "click_at", "key", "type", "scroll", "wait", "live", "drag", "move")


INVOKABLE = ("Button", "SplitButton", "MenuItem", "TabItem", "CheckBox", "RadioButton", "Hyperlink", "ListItem", "TreeItem")


class ActionError(RuntimeError):
    pass


@dataclass
class Action:
    kind: str
    label: str = ""
    role: str = ""
    button: str = "left"
    double: bool = False
    x: int = 0
    y: int = 0
    text: str = ""
    seconds: float = 0.0
    notches: int = 0
    modifiers: str = ""      # e.g. "ctrl" or "shift" held during click/drag
    to_label: str = ""       # drag destination label
    x2: int = 0
    y2: int = 0
    dx: int = 0              # relative drag offset (pixels)
    dy: int = 0
    index: int = 1           # 1 = first match, 2 = second, ...

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        if not isinstance(data, dict) or data.get("kind") not in KINDS:
            raise ActionError(f"Invalid macro step {data!r}: kind must be one of {KINDS}.")
        allowed = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        a = cls(**allowed)
        a.validate()
        return a

    def validate(self):
        if self.kind == "click" and not self.label.strip():
            raise ActionError("click needs a label")
        if self.kind in ("key", "type", "live") and not self.text:
            raise ActionError(f"{self.kind} needs text")
        if self.kind == "key":
            live.parse_shortcut(self.text)
        if self.kind == "drag" and not (self.label or (self.x or self.y)):
            raise ActionError("drag needs a start label or coordinates")
        if self.kind == "drag" and not (self.to_label or self.x2 or self.y2 or self.dx or self.dy):
            raise ActionError("drag needs a destination")
        if self.modifiers:
            live.parse_shortcut(self.modifiers)
        if not 1 <= int(self.index) <= 20:
            raise ActionError("index must be 1-20")
        if self.button not in ("left", "right", "middle"):
            raise ActionError("button must be left, right or middle")
        if self.kind == "wait" and not 0 <= self.seconds <= 30:
            raise ActionError("wait must be 0-30 seconds")
        if self.kind == "type" and len(self.text) > 500:
            raise ActionError("type text too long")

    def to_dict(self) -> dict:
        d = {"kind": self.kind}
        for k, v in asdict(self).items():
            if k != "kind" and v not in ("", 0, 0.0, False) and not (k == "button" and v == "left") and not (k == "index" and v == 1):
                d[k] = v
        return d

    def describe(self) -> str:
        mod = f"{self.modifiers}+" if self.modifiers else ""
        nth = {1: "", 2: "second ", 3: "third ", 4: "fourth "}.get(self.index, f"#{self.index} ")
        if self.kind == "drag":
            src = f"“{nth}{self.label}”" if self.label else f"{self.x},{self.y}"
            dst = f"“{self.to_label}”" if self.to_label else (f"{self.x2},{self.y2}" if (self.x2 or self.y2) else f"by {self.dx:+d},{self.dy:+d} px")
            return f"{mod}drag {src} to {dst}"
        if self.kind == "move":
            return f"move mouse to “{self.label}”" if self.label else f"move mouse to {self.x},{self.y}"
        if self.kind == "click":
            what = ("double-click" if self.double else f"{self.button}-click" if self.button != "left" else "click")
            return f"{mod}{what} “{nth}{self.label}”" + (f" ({self.role})" if self.role else "")
        if self.kind == "click_at":
            return f"{'double-' if self.double else ''}{self.button}-click at {self.x},{self.y}"
        if self.kind == "scroll":
            return f"scroll {'up' if self.notches > 0 else 'down'} {abs(self.notches)}"
        if self.kind == "wait":
            return f"wait {self.seconds:g}s"
        return f"{self.kind} “{self.text}”"

    def destructive(self) -> bool:
        if self.kind == "key":
            return self.text.casefold().replace(" ", "") in DESTRUCTIVE_KEYS
        if self.kind == "live":
            return self.text in ("delete", "render")
        if self.kind in ("click", "drag"):
            low = (self.label + " " + self.to_label).casefold()
            return any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in DESTRUCTIVE_WORDS)
        return False


# ------------------------------------------------------------------ macros
class MacroStore:
    """macros.json: {"kdenlive": {"my export": [steps]}, "resolve": {...}, "any": {...}}"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, dict[str, list[dict]]] = {"kdenlive": {}, "resolve": {}, "any": {}}
        self.errors: list[str] = []
        self.load()

    def load(self):
        self.errors = []
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.errors.append(f"macros.json unreadable: {exc}"); return
        for editor in ("kdenlive", "resolve", "any"):
            for name, steps in (raw.get(editor) or {}).items():
                try:
                    self.data[editor][self.key(name)] = [Action.from_dict(s).to_dict() for s in steps]
                except (ActionError, live.LiveControlError, TypeError) as exc:
                    self.errors.append(f"{editor}/{name}: {exc}")
        for e in self.errors:
            log.warning(e)

    @staticmethod
    def key(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().casefold())

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, editor: str, name: str) -> list[Action] | None:
        steps = self.data.get(editor, {}).get(self.key(name)) or self.data["any"].get(self.key(name))
        return [Action.from_dict(s) for s in steps] if steps else None

    def put(self, editor: str, name: str, actions: list[Action]):
        if not name.strip() or not actions:
            raise ActionError("A macro needs a name and at least one step.")
        self.data.setdefault(editor, {})[self.key(name)] = [a.to_dict() for a in actions]
        self.save()

    def delete(self, editor: str, name: str) -> bool:
        removed = self.data.get(editor, {}).pop(self.key(name), None) is not None
        self.save()
        return removed

    def names(self, editor: str) -> list[str]:
        return sorted(set(self.data.get(editor, {})) | set(self.data["any"]))


# ------------------------------------------------------------------ executor
class Executor:
    def __init__(self, backend, cfg: dict, macros: MacroStore | None = None, stop_event: threading.Event | None = None):
        self.backend, self.cfg, self.macros = backend, cfg, macros
        self.stop_event = stop_event or threading.Event()
        self.pending: tuple[str, str, list[Action]] | None = None  # (editor, description, actions)
        self.recording: tuple[str, str, list[Action]] | None = None  # (editor, name, actions)
        self._lock = threading.Lock()
        self._field_rect = None   # last clicked text field: its own typed text is not a click target
        self._typed = ""

    # recording ------------------------------------------------------------
    def start_recording(self, editor: str, name: str) -> str:
        if not name.strip():
            raise ActionError("Say a name: “record macro my export”.")
        self.recording = (editor, name.strip(), [])
        return f"Recording macro “{name}”. Say actions, then “stop recording”."

    def stop_recording(self) -> str:
        if not self.recording:
            return "Not recording."
        editor, name, steps = self.recording
        self.recording = None
        if not steps:
            return f"Macro “{name}” discarded (no steps)."
        if self.macros is None:
            raise ActionError("Macros are unavailable.")
        self.macros.put(editor, name, steps)
        return f"Saved macro “{name}” with {len(steps)} step(s) for {editor}."

    # entry points -----------------------------------------------------------
    def request(self, editor: str, actions: list[Action], description: str | None = None, confirm: bool = False) -> dict:
        """Run now, or park and ask for confirmation if anything is destructive."""
        description = description or "; ".join(a.describe() for a in actions)
        if confirm or any(a.destructive() for a in actions):
            self.pending = (editor, description, actions)
            log.info("confirmation required for: %s", description)
            return {"outcome": "needs_confirmation", "summary": f"“{description}” may be destructive. Say “confirm” to proceed or “cancel”."}
        return self._run(editor, actions, description)

    def confirm(self) -> dict | None:
        if not self.pending:
            return None
        editor, description, actions = self.pending
        self.pending = None
        log.info("confirmed by voice: %s", description)
        return self._run(editor, actions, description)

    def cancel(self) -> bool:
        had = self.pending is not None
        self.pending = None
        return had

    def run_macro(self, editor: str, name: str) -> dict:
        if self.macros is None or (steps := self.macros.get(editor, name)) is None:
            raise ActionError(f"No macro named “{name}” for {editor}.")
        return self.request(editor, steps, f"macro “{name}” ({len(steps)} steps)")

    # execution --------------------------------------------------------------
    def _run(self, editor: str, actions: list[Action], description: str) -> dict:
        if not self._lock.acquire(blocking=False):
            raise ActionError("Another action is still running.")
        try:
            self.stop_event.clear()
            done = []
            for i, action in enumerate(actions):
                if self.stop_event.is_set():
                    log.warning("stopped before step %d of %s", i + 1, description)
                    return {"outcome": "cancelled", "summary": f"Stopped after {len(done)} of {len(actions)} step(s).", "done": done}
                if action.kind != "wait" and not self.backend.focus_editor(editor):
                    raise ActionError(f"{editor.title()} is not in front; nothing more was done (completed {len(done)} step(s)).")
                done.append(self._step(editor, action))
                if self.recording and self.recording[0] == editor and len(actions) == 1 and not description.startswith("macro"):
                    self.recording[2].append(action)
            return {"outcome": "sent_unverified", "summary": "Done: " + "; ".join(done) + ". Check the editor.", "done": done}
        finally:
            self._lock.release()

    def _step(self, editor: str, a: Action) -> str:
        b = self.backend
        log.info("ui action %s: %s", editor, a.describe())
        if a.kind == "click":
            target = self.locate(editor, a.label, a.role, a.index)
            if a.role == "field":
                self._field_rect, self._typed = target.rect, ""
            plain = a.button == "left" and not a.double and not a.modifiers
            if not (plain and target.source == "uia" and target.role in INVOKABLE and b.invoke(target)):
                b.click(*target.center, a.button, a.double, a.modifiers)
            return f"{a.describe()} via {target.source} at {target.center}"
        if a.kind == "drag":
            start = self.locate(editor, a.label, a.role, a.index).center if a.label else (a.x, a.y)
            if a.to_label:
                end = self.locate(editor, a.to_label).center
            elif a.x2 or a.y2:
                end = (a.x2, a.y2)
            else:
                end = (start[0] + a.dx, start[1] + a.dy)
            b.drag(start, end, a.button, a.modifiers)
            return f"{a.describe()} {start}->{end}"
        if a.kind == "move":
            b.move(*(self.locate(editor, a.label, a.role, a.index).center if a.label else (a.x, a.y)))
        if a.kind == "click_at":
            b.click(a.x, a.y, a.button, a.double, a.modifiers)
        elif a.kind == "key":
            b.key(a.text)
        elif a.kind == "type":
            b.type_text(a.text)
            self._typed = a.text
        elif a.kind == "scroll":
            b.scroll(a.notches)
        elif a.kind == "wait":
            end = time.monotonic() + a.seconds
            while time.monotonic() < end and not self.stop_event.is_set():
                time.sleep(0.05)
        elif a.kind == "live":
            shortcuts = self.cfg["live_control"]["kdenlive_shortcuts" if editor == "kdenlive" else "resolve_shortcuts"]
            if a.text not in shortcuts:
                raise ActionError(f"No shortcut for “{a.text}” in {editor}.")
            b.key(shortcuts[a.text])
        return a.describe()

    def locate(self, editor: str, label: str, role: str = "", index: int = 1, attempts: int = 3):
        found = []
        for attempt in range(attempts):  # menus/dialogs animate in; retry briefly
            if self.stop_event.is_set():
                raise ActionError("Stopped.")
            hwnd = self.backend.editor_window(editor)
            if not hwnd:
                raise ActionError(f"{editor.title()} window is not in front.")
            labels = [part.strip() for part in label.split("|") if part.strip()]  # "Project|Sequence": alternatives in order
            uia = self.backend.uia_controls(hwnd)
            for alt in labels:
                found = rank(alt, uia, role or None)
                if found:
                    break
            if not found:  # OCR only when UI Automation has nothing
                ocr = self.backend.ocr_controls(hwnd)
                for alt in labels:
                    found = rank(alt, ocr, role or None, threshold=0.75)
                    if found:
                        break
            if found and self._field_rect and self._typed and normalize_label(label) == normalize_label(self._typed):
                fl, ft, fr, fb = self._field_rect  # skip the echo of our own typing inside the search field
                found = [t for t in found if not (ft - 4 <= t.center[1] <= fb + 4)]
            if found:
                break
            if attempt + 1 < attempts:
                time.sleep(0.35)
        if not found:
            raise ActionError(f"Could not find “{label}” in {editor.title()} (searched UI Automation and on-screen text "
                              f"{attempts}×). Nothing was clicked. Make sure it is visible, or say “click at X Y”.")
        if index > 1:
            if len(found) < index:
                raise ActionError(f"Only {len(found)} match(es) for “{label}”.")
            ordered = sorted([t for t in found if t.score >= found[0].score - 0.1], key=lambda t: (t.rect[1] // 10, t.rect[0]))
            return ordered[index - 1] if len(ordered) >= index else found[index - 1]
        best = found[0]
        if len(found) > 1 and abs(found[1].score - best.score) < 0.02 and found[1].name.casefold() != best.name.casefold():
            log.info("ambiguous label %r: %s / %s; using top-left-most", label, best.name, found[1].name)
        return best

    def list_controls(self, editor: str, limit: int = 200) -> list[dict]:
        hwnd = self.backend.editor_window(editor)
        if not hwnd:
            raise ActionError(f"{editor.title()} window is not in front.")
        return [{"name": t.name, "role": t.role, "rect": t.rect} for t in self.backend.uia_controls(hwnd)[:limit]]
