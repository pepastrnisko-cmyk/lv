"""Validated user configuration stored as JSON next to the local history.

Unknown keys are ignored, invalid values fall back to defaults and a warning is
recorded, so a hand-edited file can never stop the application from starting.
Secrets (LLM API keys) are read from environment variables named in the
config, never stored in the file itself.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    # local  = everything on this PC (Vosk/faster-whisper + rules or Ollama). Free, offline.
    # online = free-tier cloud (Groq Whisper + Groq LLM, or Google Gemini) with YOUR free API key.
    # auto   = online when a key is set and the service answers, otherwise local.
    "mode": "auto",
    "online": {
        "provider": "groq",                  # groq | gemini
        "groq_api_key_env": "GROQ_API_KEY",
        "groq_stt_model": "whisper-large-v3-turbo",
        "groq_llm_model": "llama-3.1-8b-instant",
        "gemini_api_key_env": "GEMINI_API_KEY",
        "gemini_model": "gemini-2.0-flash",
        "timeout_s": 15.0,
    },
    "voice": {
        # auto: vosk if a model is installed, else whisper if installed, else Windows SAPI.
        "engine": "auto",            # auto | vosk | whisper | sapi | off
        "vosk_model_path": "",       # empty = <data>/models/vosk (installed by setup.ps1)
        "whisper_model": "base.en",  # faster-whisper model name or path
        "language": "en",
        "wake_word": "copilot",      # empty string = every utterance is a command
        "require_wake_word": True,
        "sample_rate": 16000,
        "device": None,              # sounddevice input index/name; None = default mic
        "utterance_timeout_s": 8.0,
        "allow_voice_apply": True,   # "apply"/"confirm" applies ONLY an existing, unchanged preview
        "auto_preview": True,        # recognized edit commands are previewed (never applied) automatically
    },
    "local": {
        "llm": "rules",              # rules (built-in, no model) | ollama (free local LLM)
        "ollama_endpoint": "http://127.0.0.1:11434",
        "ollama_model": "llama3.2:3b",
        "timeout_s": 20.0,
    },
    "live_control": {
        "enabled": True,             # keyboard shortcuts into the focused editor window
        "activate_editor_window": True,
        "kdenlive_shortcuts": {
            "play": "space", "pause": "space", "undo": "ctrl+z", "redo": "ctrl+shift+z",
            "save": "ctrl+s", "cut": "shift+r", "guide": "g", "start": "home", "end": "end",
            "next frame": "right", "previous frame": "left", "in point": "i", "out point": "o",
            "delete": "delete", "render": "ctrl+return", "zoom in": "ctrl+plus", "zoom out": "ctrl+minus",
        },
        "resolve_shortcuts": {
            "play": "space", "pause": "space", "undo": "ctrl+z", "redo": "ctrl+shift+z",
            "save": "ctrl+s", "cut": "ctrl+b", "marker": "m", "start": "home", "end": "end",
            "next frame": "right", "previous frame": "left", "in point": "i", "out point": "o",
            "delete": "delete", "zoom in": "ctrl+plus", "zoom out": "ctrl+minus",
        },
    },
    "ui": {
        "first_run_done": False,
        "feedback": "beep",          # off | beep | speech (free Windows SAPI voice)
        "overlay": True,             # small always-on-top status window
        "start_with_windows": False,
        "listen_on_start": True,     # start hands-free listening automatically after the wizard
        "editor": "kdenlive",
    },
    "logging": {"level": "INFO", "max_bytes": 2_000_000, "backups": 5},
}

_CHOICES = {
    ("voice", "engine"): {"auto", "vosk", "whisper", "sapi", "off"},
    ("mode",): {"local", "online", "auto"},
    ("online", "provider"): {"groq", "gemini"},
    ("local", "llm"): {"rules", "ollama"},
    ("ui", "feedback"): {"off", "beep", "speech"},
    ("ui", "editor"): {"kdenlive", "resolve"},
    ("logging", "level"): {"DEBUG", "INFO", "WARNING", "ERROR"},
}


def config_path(directory: Path) -> Path:
    return Path(directory) / "config.json"


def _merge(defaults: dict, loaded: dict, prefix=(), warnings=None) -> dict:
    result = copy.deepcopy(defaults)
    for key, value in loaded.items():
        if key not in defaults:
            continue
        default = defaults[key]
        where = prefix + (key,)
        if isinstance(default, dict):
            if isinstance(value, dict):
                if key.endswith("_shortcuts"):  # user may add phrases
                    result[key].update({str(k).casefold(): str(v) for k, v in value.items()})
                else:
                    result[key] = _merge(default, value, where, warnings)
            else:
                warnings.append(f"{'.'.join(where)} must be an object; default used.")
            continue
        if default is None or isinstance(value, type(default)) or (isinstance(default, float) and isinstance(value, int) and not isinstance(value, bool)):
            if where in _CHOICES and value not in _CHOICES[where]:
                warnings.append(f"{'.'.join(where)}={value!r} is not one of {sorted(_CHOICES[where])}; default used.")
                continue
            result[key] = float(value) if isinstance(default, float) else value
        else:
            warnings.append(f"{'.'.join(where)} has the wrong type; default used.")
    return result


def load_config(directory: Path) -> tuple[dict, list[str]]:
    path = config_path(directory)
    warnings: list[str] = []
    loaded: dict = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("top level must be an object")
        except (OSError, ValueError) as exc:
            warnings.append(f"Could not read {path.name} ({exc}); defaults used.")
            loaded = {}
    config = _merge(DEFAULTS, loaded, (), warnings)
    for warning in warnings:
        log.warning(warning)
    return config, warnings


def write_default_config(directory: Path) -> Path:
    path = config_path(directory)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    return path


def save_config(directory: Path, config: dict) -> Path:
    path = config_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def api_key(config: dict, provider: str) -> str:
    """Key from the environment variable named in config; '' when not set."""
    name = config["online"].get(f"{provider}_api_key_env") or ""
    return os.environ.get(name, "").strip() if name else ""
