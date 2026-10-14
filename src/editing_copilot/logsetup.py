"""Rotating local log file. No audio, transcripts of secrets, or media leave the machine."""
from __future__ import annotations

import logging
import logging.handlers
import threading
from pathlib import Path

_LOCK = threading.Lock()
_HANDLER: logging.handlers.RotatingFileHandler | None = None
_PATH: Path | None = None


def setup_logging(directory: Path, level: str = "INFO", max_bytes: int = 2_000_000, backups: int = 5) -> Path:
    """Attach one rotating file handler to the ``editing_copilot`` logger.

    Calling again with the same directory is a no-op; a different directory
    closes the previous handler first so its file is released (Windows locks
    open files, which previously leaked a handle per data directory).
    """
    global _HANDLER, _PATH
    log_dir = Path(directory) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "editing-copilot.log"
    root = logging.getLogger("editing_copilot")
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    with _LOCK:
        if _HANDLER is not None and _PATH == path:
            return path
        _release_locked(root)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"))
        root.addHandler(handler)
        _HANDLER, _PATH = handler, path
    return path


def _release_locked(root: logging.Logger) -> None:
    global _HANDLER, _PATH
    if _HANDLER is not None:
        root.removeHandler(_HANDLER)
        try:
            _HANDLER.close()
        except Exception:  # closing a log must never break shutdown
            pass
    _HANDLER, _PATH = None, None


def shutdown_logging() -> None:
    """Close and detach the file handler so the log file is released."""
    with _LOCK:
        _release_locked(logging.getLogger("editing_copilot"))