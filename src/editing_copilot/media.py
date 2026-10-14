"""Read-only media metadata via ffprobe. Degrades gracefully when ffprobe is absent.

Never modifies media: ffprobe is run with an argument list (no shell), a
timeout, and only reads the file header/streams.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

FFPROBE_TIMEOUT = 15
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_ffprobe(explicit: str | os.PathLike[str] | None = None) -> str | None:
    """Explicit path, then EC_FFPROBE env var, then PATH. None when not found."""
    for candidate in (explicit, os.environ.get("EC_FFPROBE")):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return shutil.which("ffprobe")


def _rate(value) -> float | None:
    try:
        rate = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None
    return round(float(rate), 3) if rate > 0 else None


def _number(value, kind=float):
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def summarize(raw: dict) -> dict:
    fmt = raw.get("format") or {}
    streams = []
    for s in raw.get("streams") or []:
        kind = s.get("codec_type")
        entry = {"index": s.get("index"), "type": kind, "codec": s.get("codec_name")}
        if kind == "video":
            entry.update(width=_number(s.get("width"), int), height=_number(s.get("height"), int),
                         fps=_rate(s.get("avg_frame_rate")) or _rate(s.get("r_frame_rate")),
                         pix_fmt=s.get("pix_fmt"))
        elif kind == "audio":
            entry.update(sample_rate=_number(s.get("sample_rate"), int), channels=_number(s.get("channels"), int))
        streams.append(entry)
    return {"format": fmt.get("format_name"), "duration_seconds": _number(fmt.get("duration")),
            "size_bytes": _number(fmt.get("size"), int), "bit_rate": _number(fmt.get("bit_rate"), int),
            "streams": streams}


def probe_media(path: str | os.PathLike[str], ffprobe: str | None = None, timeout: float = FFPROBE_TIMEOUT,
                runner=subprocess.run) -> dict:
    """Return ``{"available", "ok", ...}``; never raises for missing tools or bad files."""
    target = Path(path)
    tool = find_ffprobe(ffprobe)
    if tool is None:
        return {"path": str(target), "available": False, "ok": False,
                "error": "ffprobe not found (install FFmpeg or set EC_FFPROBE)."}
    if not target.is_file():
        return {"path": str(target), "available": True, "ok": False, "error": "File not found."}
    command = [tool, "-v", "error", "-hide_banner", "-print_format", "json", "-show_format", "-show_streams", "--", str(target)]
    try:
        done = runner(command, capture_output=True, timeout=timeout, check=False, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"path": str(target), "available": True, "ok": False, "error": f"ffprobe timed out after {timeout}s."}
    except OSError as exc:
        return {"path": str(target), "available": False, "ok": False, "error": f"ffprobe could not start: {exc}"}
    if done.returncode != 0:
        message = (done.stderr or b"").decode("utf-8", "replace").strip()[:500]
        return {"path": str(target), "available": True, "ok": False, "error": message or f"ffprobe exit code {done.returncode}."}
    try:
        raw = json.loads((done.stdout or b"{}").decode("utf-8", "replace"))
    except ValueError:
        return {"path": str(target), "available": True, "ok": False, "error": "ffprobe returned invalid JSON."}
    return {"path": str(target), "available": True, "ok": True, **summarize(raw)}
