"""Windows UI layer: find on-screen controls (UI Automation, then OCR) and drive mouse/keyboard.

Kept behind a small backend interface so the safety logic in :mod:`actions`
can be tested with a mock. Resolve's Qt UI exposes few UIA elements, so OCR on
a screenshot of the editor window is the fallback. Everything is free/local:
pywinauto (UIA), rapidocr-onnxruntime (OCR), Pillow (screenshot).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ctypes
import difflib
import logging
import os
import re
import time

from . import live

log = logging.getLogger(__name__)

ROLE_MAP = {"button": ("Button", "SplitButton"), "tab": ("TabItem",), "menu": ("MenuItem", "MenuBar"),
            "field": ("Edit", "ComboBox", "Spinner"), "checkbox": ("CheckBox",), "item": ("ListItem", "TreeItem", "DataItem"),
            "panel": ("Pane", "Group", "TabItem", "Window"), "slider": ("Slider",)}


@dataclass
class Target:
    name: str
    role: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom (screen pixels)
    source: str = "uia"              # uia | ocr
    score: float = 1.0
    invoke: object = field(default=None, repr=False, compare=False)

    @property
    def center(self):
        left, top, right, bottom = self.rect
        return (left + right) // 2, (top + bottom) // 2


def normalize_label(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")              # Qt rich-text labels "<b>..</b>"
    text = re.sub(r"&(?=\w)", "", text)                   # Qt mnemonics "&File"
    text = re.sub(r"\s*\(?(ctrl|shift|alt)\+[\w+]+\)?\s*$", "", text, flags=re.I)
    text = re.sub(r"[.…:]+$", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def match_score(wanted: str, name: str) -> float:
    w, n = normalize_label(wanted), normalize_label(name)
    if not w or not n:
        return 0.0
    if w == n:
        return 1.0
    if re.search(r"\b" + re.escape(w) + r"\b", n):
        return 0.9 - min(0.3, (len(n) - len(w)) / 100)
    return difflib.SequenceMatcher(None, w, n).ratio() * 0.85


def rank(wanted: str, candidates: list[Target], role: str | None = None, threshold: float = 0.72) -> list[Target]:
    roles = ROLE_MAP.get(role or "", ())
    scored = []
    for c in candidates:
        s = match_score(wanted, c.name)
        if roles and c.role in roles:
            s += 0.05
        elif roles and c.source == "uia" and c.role not in roles:
            s -= 0.1
        if s >= threshold:
            c.score = s
            scored.append(c)
    return sorted(scored, key=lambda c: (-c.score, c.source != "uia", c.rect[1], c.rect[0]))


class WindowsBackend:
    """Real Windows implementation (UIA via pywinauto, OCR via rapidocr)."""

    def __init__(self, uia_budget_s: float = 2.5, max_elements: int = 4000):
        if os.name != "nt":
            raise RuntimeError("UI automation is only available on Windows.")
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor: UIA/OCR/mouse share pixel space
        except Exception:
            try: ctypes.windll.user32.SetProcessDPIAware()
            except Exception: pass
        self.uia_budget_s, self.max_elements = uia_budget_s, max_elements
        self._ocr = None
        self._ocr_cache: dict = {}  # (hwnd, rect, image fingerprint) -> targets

    # -- windows
    def foreground_process(self) -> str:
        return live._process_name(ctypes.windll.user32.GetForegroundWindow())

    def editor_window(self, editor: str):
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if live._process_name(hwnd) in live.PROCESSES[editor]:
            return hwnd
        return None

    def focus_editor(self, editor: str) -> bool:
        names = live.PROCESSES[editor]
        if self.foreground_process() in names:
            return True
        hwnd = live._find_window(names)
        if not hwnd:
            return False
        live.force_foreground(hwnd)
        return self.foreground_process() in names

    def window_rect(self, hwnd):
        from ctypes import wintypes
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    # -- discovery
    def uia_controls(self, hwnd) -> list[Target]:
        try:
            from pywinauto import Desktop
        except ImportError:
            log.warning("pywinauto not installed; UIA search disabled")
            return []
        out, started = [], time.monotonic()
        try:
            root = Desktop(backend="uia").window(handle=hwnd).wrapper_object()
            stack = [root]
            # also include popup menus owned by the same process (open menus are separate top-level windows)
            pid = root.process_id()
            for w in Desktop(backend="uia").windows(process=pid):
                if w.handle != hwnd:
                    stack.append(w)
            while stack and len(out) < self.max_elements and time.monotonic() - started < self.uia_budget_s:
                el = stack.pop()
                try:
                    info = el.element_info
                    name, role = info.name or "", info.control_type or ""
                    rect = info.rectangle
                    if name and rect.width() > 0 and rect.height() > 0 and el.is_visible():
                        out.append(Target(name, role, (rect.left, rect.top, rect.right, rect.bottom), "uia", invoke=el))
                    stack.extend(el.children())
                except Exception:
                    continue
        except Exception as exc:
            log.warning("UIA enumeration failed: %s", exc)
        return out

    def ocr_controls(self, hwnd) -> list[Target]:
        try:
            from PIL import ImageGrab
            import numpy as np
            if self._ocr is None:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
        except ImportError:
            log.warning("OCR packages not installed (rapidocr-onnxruntime, pillow)")
            return []
        left, top, right, bottom = self.window_rect(hwnd)
        if right - left < 40 or bottom - top < 40:  # minimised / off-screen
            return []
        img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        import hashlib
        # coarse fingerprint: ignores small changes (playhead, timecode, meters) so the cache actually hits
        small = img.convert("L").resize((32, 20)).point(lambda v: v // 64)
        fingerprint = hashlib.blake2b(small.tobytes(), digest_size=12).hexdigest()
        key = (hwnd, (left, top, right, bottom), fingerprint)
        if key in self._ocr_cache:  # unchanged screen -> reuse (OCR is the slow part)
            return list(self._ocr_cache[key])
        scale = 1.0
        if img.width > 1700:  # large/4K windows: downscale for speed, map coordinates back
            scale = 1700 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        try:
            try:
                result, _ = self._ocr(np.array(img), use_cls=False)  # text is upright: skip the angle classifier (faster)
            except TypeError:
                result, _ = self._ocr(np.array(img))
        except Exception as exc:  # OCR engine errors must never break the action
            log.warning("OCR failed: %s", exc)
            return []
        out = []
        for box, text, score in result or []:
            xs, ys = [p[0] / scale for p in box], [p[1] / scale for p in box]
            out.append(Target(text, "Text", (int(min(xs)) + left, int(min(ys)) + top, int(max(xs)) + left, int(max(ys)) + top), "ocr", float(score)))
        if len(self._ocr_cache) > 8:
            self._ocr_cache.clear()
        self._ocr_cache[key] = list(out)
        return out  # image is never saved

    # -- input
    _BUTTONS = {"left": (0x2, 0x4), "right": (0x8, 0x10), "middle": (0x20, 0x40)}

    def _mods(self, modifiers: str, down: bool):
        if not modifiers:
            return
        user32 = ctypes.windll.user32
        vks = live.parse_shortcut(modifiers)
        for vk in (vks if down else reversed(vks)):
            user32.keybd_event(vk, 0, 0 if down else 2, 0)

    def move(self, x: int, y: int):
        ctypes.windll.user32.SetCursorPos(int(x), int(y)); time.sleep(0.05)

    def click(self, x: int, y: int, button: str = "left", double: bool = False, modifiers: str = ""):
        user32 = ctypes.windll.user32
        self.move(x, y)
        down, up = self._BUTTONS[button]
        self._mods(modifiers, True)
        try:
            for _ in range(2 if double else 1):
                user32.mouse_event(down, 0, 0, 0, 0); user32.mouse_event(up, 0, 0, 0, 0); time.sleep(0.06)
        finally:
            self._mods(modifiers, False)

    def drag(self, start, end, button: str = "left", modifiers: str = "", steps: int = 25):
        """Human-like press, move in steps (so Qt sees a drag), release."""
        user32 = ctypes.windll.user32
        down, up = self._BUTTONS[button]
        self.move(*start)
        self._mods(modifiers, True)
        try:
            user32.mouse_event(down, 0, 0, 0, 0); time.sleep(0.12)
            for i in range(1, steps + 1):
                user32.SetCursorPos(int(start[0] + (end[0] - start[0]) * i / steps), int(start[1] + (end[1] - start[1]) * i / steps))
                time.sleep(0.015)
            time.sleep(0.1)
        finally:
            user32.mouse_event(up, 0, 0, 0, 0)
            self._mods(modifiers, False)

    def invoke(self, target: Target) -> bool:
        """Prefer a real UIA Invoke/Select (no mouse); False if not supported."""
        el = target.invoke
        if el is None:
            return False
        for method in ("invoke", "select", "expand"):
            fn = getattr(el, method, None)
            if fn:
                try:
                    fn(); return True
                except Exception:
                    continue
        return False

    def key(self, spec: str):
        live._send(live.parse_shortcut(spec))

    def type_text(self, text: str):
        for ch in text:
            self._unicode(ch)
            time.sleep(0.005)

    def _unicode(self, ch):
        class KI(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

        class U(ctypes.Union):
            _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 32)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("u", U)]
        arr = (INPUT * 2)()
        for i, flags in enumerate((0x4, 0x4 | 0x2)):
            arr[i].type = 1; arr[i].u.ki = KI(0, ord(ch), flags, 0, 0)
        ctypes.windll.user32.SendInput(2, arr, ctypes.sizeof(INPUT))

    def scroll(self, notches: int):
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(notches) * 120, 0)
