"""English voice input: local (Vosk / faster-whisper / Windows SAPI) or online (Groq Whisper, Gemini).

A :class:`VoiceListener` records utterances from the microphone with a simple
energy-based endpoint detector and hands text to a callback on its own thread.
Audio stays in memory; online mode uploads only the short utterance WAV to the
provider the user selected. Nothing is written to disk.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave

from .config import api_key

log = logging.getLogger(__name__)
LANGUAGE = "en"  # English-only by product decision


class VoiceError(RuntimeError):
    pass


def default_vosk_model(data_dir: Path) -> Path:
    return Path(data_dir) / "models" / "vosk-model-small-en-us-0.15"


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


def rms(pcm: bytes) -> float:
    import array
    a = array.array("h", pcm[: len(pcm) - len(pcm) % 2])
    return (sum(x * x for x in a) / len(a)) ** 0.5 if a else 0.0


# ---------------------------------------------------------------- recognizers
class VoskRecognizer:
    name = "vosk (local)"

    def __init__(self, model_path: Path, rate: int):
        try:
            import vosk
        except ImportError as exc:
            raise VoiceError("Vosk is not installed (pip install vosk).") from exc
        if not Path(model_path).is_dir():
            raise VoiceError(f"Vosk English model not found at {model_path}. Re-run Install.cmd to download it.")
        vosk.SetLogLevel(-1)
        self._model, self._rate, self._vosk = vosk.Model(str(model_path)), rate, vosk

    def transcribe(self, pcm: bytes) -> str:
        rec = self._vosk.KaldiRecognizer(self._model, self._rate)
        rec.AcceptWaveform(pcm)
        return json.loads(rec.FinalResult()).get("text", "")


class WhisperRecognizer:
    name = "faster-whisper (local)"

    def __init__(self, model: str, rate: int):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise VoiceError("faster-whisper is not installed (pip install faster-whisper).") from exc
        if not model.endswith(".en") and "/" not in model and "\\" not in model:
            model += ".en"
        self._model, self._rate = WhisperModel(model, device="cpu", compute_type="int8"), rate

    def transcribe(self, pcm: bytes) -> str:
        import numpy as np
        audio = np.frombuffer(pcm, dtype=np.int16).astype("float32") / 32768.0
        segments, _ = self._model.transcribe(audio, language=LANGUAGE, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()


def _http(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        raise VoiceError(f"Online speech service returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise VoiceError(f"Online speech service unreachable: {exc}") from exc


class GroqRecognizer:
    name = "Groq Whisper (online, free tier)"

    def __init__(self, cfg: dict, rate: int):
        self._key, self._cfg, self._rate = api_key(cfg, "groq"), cfg["online"], rate
        if not self._key:
            raise VoiceError("GROQ_API_KEY is not set.")

    def transcribe(self, pcm: bytes) -> str:
        boundary = uuid.uuid4().hex
        wav = pcm_to_wav(pcm, self._rate)
        parts = []
        for k, v in (("model", self._cfg["groq_stt_model"]), ("language", LANGUAGE), ("response_format", "json"), ("temperature", "0")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="u.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode() + wav + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=b"".join(parts), method="POST",
                                     headers={"Authorization": "Bearer " + self._key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        return _http(req, self._cfg["timeout_s"]).get("text", "").strip()


class GeminiRecognizer:
    name = "Google Gemini (online, free tier)"

    def __init__(self, cfg: dict, rate: int):
        self._key, self._cfg, self._rate = api_key(cfg, "gemini"), cfg["online"], rate
        if not self._key:
            raise VoiceError("GEMINI_API_KEY is not set.")

    def transcribe(self, pcm: bytes) -> str:
        body = {"contents": [{"parts": [
            {"text": "Transcribe this English speech verbatim. Output only the transcript."},
            {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(pcm_to_wav(pcm, self._rate)).decode()}}]}],
            "generationConfig": {"temperature": 0}}
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{self._cfg['gemini_model']}:generateContent",
                                     data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self._key})
        data = _http(req, self._cfg["timeout_s"])
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError) as exc:
            raise VoiceError("Gemini returned no transcript.") from exc


def _local(cfg: dict, data_dir: Path):
    v, rate = cfg["voice"], cfg["voice"]["sample_rate"]
    order = {"vosk": ["vosk"], "whisper": ["whisper"]}.get(v["engine"], ["vosk", "whisper"])
    errors = []
    for name in order:
        try:
            if name == "vosk":
                return VoskRecognizer(Path(v["vosk_model_path"] or default_vosk_model(data_dir)), rate)
            return WhisperRecognizer(v["whisper_model"], rate)
        except VoiceError as exc:
            errors.append(str(exc))
    raise VoiceError("No local recognizer: " + " | ".join(errors))


def _online(cfg: dict):
    rate = cfg["voice"]["sample_rate"]
    return GeminiRecognizer(cfg, rate) if cfg["online"]["provider"] == "gemini" else GroqRecognizer(cfg, rate)


class FallbackRecognizer:
    """auto mode: try online, permanently-for-session fall back to local after a failure."""

    def __init__(self, primary, secondary_factory):
        self.primary, self._factory, self.secondary = primary, secondary_factory, None
        self.name = f"{primary.name} → local fallback"

    def transcribe(self, pcm: bytes) -> str:
        if self.primary is not None:
            try:
                return self.primary.transcribe(pcm)
            except VoiceError as exc:
                log.warning("online recognizer failed, switching to local: %s", exc)
                self.primary = None
        if self.secondary is None:
            self.secondary = self._factory()
        self.name = self.secondary.name
        return self.secondary.transcribe(pcm)


def build_recognizer(cfg: dict, data_dir: Path):
    mode = cfg["mode"]
    if cfg["voice"]["engine"] == "off":
        raise VoiceError("Voice is turned off in config.")
    if mode == "online":
        return _online(cfg)
    if mode == "local":
        return _local(cfg, data_dir)
    try:
        return FallbackRecognizer(_online(cfg), lambda: _local(cfg, data_dir))
    except VoiceError:
        return _local(cfg, data_dir)


# ---------------------------------------------------------------- microphone
class VoiceListener:
    """Continuous, hands-free listening. on_text(text) runs on the listener thread."""

    def __init__(self, recognizer, on_text, on_error, *, rate=16000, device=None,
                 threshold=500.0, silence_s=0.8, max_s=8.0, stream_factory=None):
        self.recognizer, self.on_text, self.on_error = recognizer, on_text, on_error
        self.rate, self.device, self.threshold, self.silence_s, self.max_s = rate, device, threshold, silence_s, max_s
        self._stop = threading.Event()
        self._stream_factory = stream_factory
        self.thread = threading.Thread(target=self._run, name="EditingCopilot-voice", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _open(self):
        if self._stream_factory:
            return self._stream_factory()
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceError("sounddevice is not installed (pip install sounddevice).") from exc
        try:
            stream = sd.RawInputStream(samplerate=self.rate, blocksize=self.rate // 10, dtype="int16", channels=1, device=self.device)
        except Exception as exc:  # PortAudio errors
            raise VoiceError(f"Microphone unavailable: {exc}") from exc
        stream.start()
        return stream

    def _run(self):
        try:
            stream = self._open()
        except VoiceError as exc:
            self.on_error(str(exc)); return
        chunk = self.rate // 10
        try:
            buf, speaking, quiet, started = bytearray(), False, 0.0, 0.0
            while not self._stop.is_set():
                data, _ = stream.read(chunk)
                data = bytes(data)
                if not data:
                    break
                loud = rms(data) >= self.threshold
                if loud and not speaking:
                    speaking, started, buf = True, time.monotonic(), bytearray()
                if speaking:
                    buf += data
                    quiet = 0.0 if loud else quiet + 0.1
                    if quiet >= self.silence_s or time.monotonic() - started >= self.max_s:
                        speaking = False
                        if len(buf) > self.rate * 2 * 0.3:  # at least 0.3 s
                            try:
                                text = self.recognizer.transcribe(bytes(buf)).strip()
                            except VoiceError as exc:
                                self.on_error(str(exc)); continue
                            except Exception as exc:  # recognizer bug must not kill listener
                                log.exception("recognizer crashed"); self.on_error(f"Recognizer error: {exc}"); continue
                            if text and not self._stop.is_set():
                                self.on_text(text)
        finally:
            for name in ("stop", "close"):
                try: getattr(stream, name)()
                except Exception: pass


def voice_status(cfg: dict, data_dir: Path) -> tuple[bool, str]:
    try:
        r = build_recognizer(cfg, data_dir)
    except VoiceError as exc:
        return False, str(exc)
    return True, f"Voice ready: {r.name}"
