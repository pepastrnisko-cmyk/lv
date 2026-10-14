"""Optional LLM fallback that maps free-form English to ONE canonical command.

Backends (all free): built-in rules (default, no model), Ollama (local),
Groq free tier and Google Gemini free tier (online, user-supplied key).
The model output is never executed: it must parse with ``parse_command`` and
still goes through Preview; anything else is rejected.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .commands import UnsupportedCommand, parse_command
from .config import api_key
from .nlu import Intent, interpret, normalize

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You convert a video editor's spoken English request into exactly ONE command line.
Allowed commands (frames are integers, zero-based timeline frames):
inspect
list clips
add marker at frame N named "NAME" color COLOR   (Resolve; colors: Blue Cyan Green Yellow Red Pink Purple)
add guide at frame N named "NAME"                (Kdenlive)
split clip selected at frame N
trim clip selected end by N frames
undo
Convert seconds to frames with FPS={fps}. If the request cannot be expressed with these commands,
reply exactly: UNSUPPORTED
Reply with the command line only, no explanation."""


class AssistantError(RuntimeError):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https/localhost URLs
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AssistantError(f"HTTP {exc.code} from assistant service") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise AssistantError(f"Assistant service unreachable: {exc}") from exc


def ask_ollama(cfg: dict, prompt: str, system: str) -> str:
    local = cfg["local"]
    data = _post(local["ollama_endpoint"].rstrip("/") + "/api/chat",
                 {"model": local["ollama_model"], "stream": False, "options": {"temperature": 0},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                 {}, local["timeout_s"])
    return data.get("message", {}).get("content", "")


def ask_groq(cfg: dict, prompt: str, system: str) -> str:
    key = api_key(cfg, "groq")
    if not key:
        raise AssistantError("GROQ_API_KEY is not set.")
    data = _post("https://api.groq.com/openai/v1/chat/completions",
                 {"model": cfg["online"]["groq_llm_model"], "temperature": 0, "max_tokens": 80,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                 {"Authorization": "Bearer " + key}, cfg["online"]["timeout_s"])
    return data["choices"][0]["message"]["content"]


def ask_gemini(cfg: dict, prompt: str, system: str) -> str:
    key = api_key(cfg, "gemini")
    if not key:
        raise AssistantError("GEMINI_API_KEY is not set.")
    model = cfg["online"]["gemini_model"]
    data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                 {"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0, "maxOutputTokens": 80}},
                 {"x-goog-api-key": key}, cfg["online"]["timeout_s"])
    return data["candidates"][0]["content"]["parts"][0]["text"]


def online_available(cfg: dict) -> bool:
    return bool(api_key(cfg, cfg["online"]["provider"]))


def llm_chain(cfg: dict) -> list[tuple[str, callable]]:
    """Ordered backends for the configured mode. Rules always run first, outside this chain."""
    mode = cfg["mode"]
    online = [("gemini", ask_gemini)] if cfg["online"]["provider"] == "gemini" else [("groq", ask_groq)]
    local = [("ollama", ask_ollama)] if cfg["local"]["llm"] == "ollama" else []
    if mode == "online":
        return online
    if mode == "local":
        return local
    return (online if online_available(cfg) else []) + local


def understand(utterance: str, cfg: dict, fps: float = 25.0, editor: str = "kdenlive") -> Intent:
    intent = interpret(utterance, fps, editor)
    if intent.kind != "unknown":
        return intent
    system = SYSTEM_PROMPT.format(fps=fps)
    for name, ask in llm_chain(cfg):
        try:
            answer = (ask(cfg, utterance, system) or "").strip().strip("`").splitlines()[0].strip()
        except (AssistantError, KeyError, IndexError, TypeError) as exc:
            log.warning("assistant backend %s failed: %s", name, exc)
            continue
        if answer.upper() == "UNSUPPORTED":
            return Intent("unknown", utterance, utterance)
        candidate = normalize(answer, fps)
        try:
            parse_command(candidate)
        except UnsupportedCommand:
            log.info("assistant %s returned non-grammar output; rejected", name)
            continue
        log.info("assistant %s mapped utterance to %r", name, candidate)
        return Intent("command", candidate, utterance)
    return intent
