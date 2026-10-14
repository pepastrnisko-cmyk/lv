"""Optional Windows hotkey and push-to-talk dictation, never auto-execute."""
import ctypes
from ctypes import wintypes
import os
import threading
import time


class StopHotkey:
    def __init__(self, callback):
        self.callback, self.thread_id, self.available = callback, None, False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        if os.name != 'nt':
            return
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        # Ctrl + Shift + Space, with repeat disabled.
        if not user32.RegisterHotKey(None, 71, 0x4000 | 0x0002 | 0x0004, 0x20):
            return
        self.available = True
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, 71)
            self.available = False

    def close(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)


def voice_available():
    if os.name != 'nt':
        return False, 'Windows offline dictation is unavailable on this platform.'
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            engine = win32com.client.Dispatch('SAPI.SpInprocRecognizer')
            tokens = engine.GetRecognizers()
            count = tokens.Count
            return bool(count), f'{count} installed Windows speech recognizer(s).'
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        return False, 'No usable installed Windows speech recognizer. Typed commands remain available.'


def dictate_once(callback, on_error, cancel, timeout=12):
    """Mic access begins only when the user presses Dictate; no cloud provider."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        recognizer = None
        try:
            recognizer = win32com.client.Dispatch('SAPI.SpInprocRecognizer')
            recognizer.AudioInput = recognizer.GetAudioInputs().Item(0)
            context = recognizer.CreateRecoContext()
            received = []
            class Events:
                def OnRecognition(self, stream_number, stream_position, recognition_type, result):
                    received.append(result.PhraseInfo.GetText())
            handler = win32com.client.WithEvents(context, Events)  # noqa: F841 - keeps the COM event sink alive
            grammar = context.CreateGrammar(1)
            grammar.DictationLoad()
            grammar.DictationSetState(1)
            started = time.monotonic()
            while not cancel.is_set() and not received and time.monotonic() - started < timeout:
                pythoncom.PumpWaitingMessages()
                time.sleep(.02)
            grammar.DictationSetState(0)
            recognizer.State = 0
            if received and not cancel.is_set():
                callback(received[0])
            elif not cancel.is_set():
                on_error('No speech recognized. Type a command or try again.')
        finally:
            if recognizer is not None:
                try: recognizer.State = 0
                except Exception: pass
            pythoncom.CoUninitialize()
    except Exception as exc:
        on_error('Windows dictation is unavailable: ' + str(exc))
