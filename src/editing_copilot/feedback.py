"""Audible feedback, user environment variables, start-with-Windows, crash logging (Windows-safe no-ops elsewhere)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import threading
import traceback

log = logging.getLogger(__name__)


class Speaker:
    """Free Windows SAPI text-to-speech (async), or short beeps. Never blocks the UI."""

    def __init__(self, mode: str = "beep"):
        self.mode = mode  # off | beep | speech
        self._lock = threading.Lock()

    def _speak(self, text: str):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voice.Rate = 1
                voice.Speak(text[:200], 0)
            finally:
                pythoncom.CoUninitialize()
        except Exception as exc:
            log.info("TTS unavailable: %s", exc)

    def _beep(self, kind: str):
        try:
            import winsound
            winsound.Beep(*{"ok": (880, 90), "listen": (660, 60), "error": (300, 220), "confirm": (520, 160)}.get(kind, (700, 80)))
        except Exception:
            pass

    def say(self, text: str, kind: str = "ok"):
        if self.mode == "off" or os.name != "nt":
            return
        target = (lambda: self._speak(text)) if self.mode == "speech" else (lambda: self._beep(kind))

        def run():
            with self._lock:
                target()
        threading.Thread(target=run, name="EditingCopilot-tts", daemon=True).start()


def set_user_env(name: str, value: str) -> None:
    """Store in HKCU\\Environment (like setx) and the current process. Never written to config files."""
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("invalid variable name")
    os.environ[name] = value
    if os.name != "nt":
        return
    import ctypes
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        if value:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        else:
            try: winreg.DeleteValue(key, name)
            except FileNotFoundError: pass
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 2000, None)


def load_user_env(names) -> None:
    """Pick up keys saved after this process started (e.g. by the wizard in another session)."""
    if os.name != "nt":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for n in names:
                if n and not os.environ.get(n):
                    try:
                        os.environ[n] = winreg.QueryValueEx(key, n)[0]
                    except FileNotFoundError:
                        pass
    except OSError:
        pass


def startup_shortcut_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Editing Copilot.lnk"


def set_start_with_windows(enabled: bool) -> bool:
    path = startup_shortcut_path()
    if not enabled:
        path.unlink(missing_ok=True); return False
    if os.name != "nt":
        return False
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    link = shell.CreateShortcut(str(path))
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if getattr(sys, "frozen", False):
        link.TargetPath, link.Arguments = str(exe), "--minimized"
    else:
        link.TargetPath, link.Arguments = str(pythonw if pythonw.exists() else exe), "-m editing_copilot --minimized"
    link.WorkingDirectory = str(Path.home())
    link.Save()
    return True


def install_crash_logging(directory: Path) -> Path:
    crash = Path(directory) / "logs" / "crash.log"
    crash.parent.mkdir(parents=True, exist_ok=True)

    def write(kind, exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("editing_copilot").error("%s: %s", kind, text)
        try:
            with crash.open("a", encoding="utf-8") as fh:
                import datetime
                fh.write(f"\n=== {datetime.datetime.now().isoformat(timespec='seconds')} {kind}\n{text}")
        except OSError:
            pass

    previous = sys.excepthook

    def hook(t, e, tb):
        write("unhandled", t, e, tb)
        previous(t, e, tb)
    sys.excepthook = hook
    threading.excepthook = lambda args: write(f"thread {args.thread.name if args.thread else '?'}", args.exc_type, args.exc_value, args.exc_traceback)
    install_crash_logging.write = write  # used by Tk report_callback_exception
    return crash
