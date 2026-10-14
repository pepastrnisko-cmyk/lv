"""Rotating local log file. No audio, transcripts of secrets, or media leave the machine."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_CONFIGURED = False


def setup_logging(directory: Path, level: str = "INFO", max_bytes: int = 2_000_000, backups: int = 5) -> Path:
    global _CONFIGURED
    log_dir = Path(directory) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "editing-copilot.log"
    root = logging.getLogger("editing_copilot")
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    if not _CONFIGURED:
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"))
        root.addHandler(handler)
        _CONFIGURED = True
    return path
