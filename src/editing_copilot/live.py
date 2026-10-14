"""Live editor control by keyboard shortcuts (Windows).

Kdenlive has no public plugin/automation API on Windows (its D-Bus interface is
Linux-only and undocumented), and DaVinci Resolve *free* blocks external
scripting. Keyboard shortcuts work in both, so live transport/cut/marker
commands are sent as keystrokes - but ONLY after verifying that the foreground
window belongs to the editor process. The result is reported as
"sent - not verified" because a keystroke has no observable postcondition.
"""
from __future__ import annotations

import ctypes
import logging
import os
import time

log = logging.getLogger(__name__)

PROCESSES = {"kdenlive": ("kdenlive.exe",), "resolve": ("resolve.exe",)}
VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "space": 0x20, "return": 0x0D, "enter": 0x0D, "home": 0x24,
      "end": 0x23, "left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28, "delete": 0x2E, "plus": 0xBB,
      "minus": 0xBD, "backslash": 0xDC, "escape": 0x1B, "tab": 0x09, "backspace": 0x08, "win": 0x5B, "windows": 0x5B, "apps": 0x5D,
      "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "comma": 0xBC, "period": 0xBE}
VK.update({chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})
VK.update({f"f{n}": 0x6F + n for n in range(1, 13)})
EXTENDED = {0x24, 0x23, 0x25, 0x27, 0x26, 0x28, 0x2E}


class LiveControlError(RuntimeError):
    pass


def parse_shortcut(spec: str) -> list[int]:
    keys = [k.strip().casefold() for k in spec.split("+") if k.strip()]
    if spec.strip().endswith("++"):
        keys.append("plus")
    if not keys or any(k not in VK for k in keys):
        raise LiveControlError(f"Unsupported shortcut {spec!r}.")
    return [VK[k] for k in keys]


def _process_name(hwnd) -> str:
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768); size = ctypes.c_ulong(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).casefold()
    finally:
        kernel32.CloseHandle(handle)


def _find_window(names) -> int | None:
    user32 = ctypes.windll.user32
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    from ctypes import wintypes

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) and _process_name(hwnd) in names:
            buf = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(hwnd, buf, 256)
            if "splash" in buf.value.casefold():
                return True  # editor still starting
            r = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True
    user32.EnumWindows(proto(cb), 0)
    return max(found)[1] if found else None  # the main window is the largest one


def force_foreground(hwnd) -> bool:
    """Bring hwnd to the front despite Windows' foreground lock (background apps may not steal focus).
    Uses the documented-safe sequence: restore, a harmless Alt tap (grants foreground rights),
    AttachThreadInput to the current foreground thread, SetForegroundWindow/BringWindowToTop."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    for attempt in range(3):
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return True
        user32.keybd_event(0x12, 0, 0, 0); user32.keybd_event(0x12, 0, 2, 0)  # Alt down/up
        fg_thread = user32.GetWindowThreadProcessId(fg, None)
        me = kernel32.GetCurrentThreadId()
        attached = fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True)
        try:
            user32.ShowWindow(hwnd, 5)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(me, fg_thread, False)
        time.sleep(0.25 + 0.15 * attempt)
    return user32.GetForegroundWindow() == hwnd or _process_name(user32.GetForegroundWindow()) == _process_name(hwnd)


def _send(vks: list[int]):
    class KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

    class U(ctypes.Union):
        _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 32)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", U)]
    seq = [(vk, 0) for vk in vks] + [(vk, 2) for vk in reversed(vks)]
    arr = (INPUT * len(seq))()
    for i, (vk, up) in enumerate(seq):
        arr[i].type = 1
        arr[i].u.ki = KI(vk, 0, up | (1 if vk in EXTENDED else 0), 0, 0)
    if ctypes.windll.user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT)) != len(seq):
        raise LiveControlError("Windows blocked the keystroke (UIPI: is the editor running as administrator?).")


def send_action(editor: str, action: str, cfg: dict) -> dict:
    live = cfg["live_control"]
    if not live["enabled"]:
        raise LiveControlError("Live control is disabled in config.")
    shortcuts = live["kdenlive_shortcuts" if editor == "kdenlive" else "resolve_shortcuts"]
    if action not in shortcuts:
        raise LiveControlError(f"'{action}' has no shortcut configured for {editor}.")
    vks = parse_shortcut(shortcuts[action])
    if os.name != "nt":
        raise LiveControlError("Live keyboard control is only available on Windows.")
    names = PROCESSES[editor]
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if _process_name(hwnd) not in names:
        if not live["activate_editor_window"]:
            raise LiveControlError(f"Bring {editor.title()} to the front first.")
        hwnd = _find_window(names)
        if not hwnd:
            raise LiveControlError(f"{editor.title()} is not running.")
        force_foreground(hwnd)
        if _process_name(user32.GetForegroundWindow()) not in names:
            raise LiveControlError(f"Windows did not allow focusing {editor.title()}; click its window and repeat.")
    _send(vks)
    log.info("live %s action %s sent as %s", editor, action, shortcuts[action])
    return {"outcome": "sent_unverified", "action": action, "shortcut": shortcuts[action],
            "summary": f"Sent '{shortcuts[action]}' ({action}) to {editor.title()}. Keystrokes cannot be verified; check the editor."}
