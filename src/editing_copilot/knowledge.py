"""Bundled Kdenlive + colour-grading master reference (user-supplied) as a searchable knowledge base.

"how do I ..." / "explain ..." voice requests return the most relevant sections.
If an LLM backend is configured (Ollama, Groq or Gemini, all free) it may
summarise those sections, constrained to the retrieved text. Authority rules
from the reference (Part 0) are applied: grading questions prefer Part 1 and K7,
and answers remind the user to confirm names on screen.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from pathlib import Path
import re

log = logging.getLogger(__name__)
_HEAD = re.compile(r"^(Part \d+(?:\.\d+)?: .+|K\d+: [A-Z].+)$")
_STOP = set("a an the and or of to in on for with how do i is it my what can you me about tell explain does this that".split())
_TOPIC_BOOST = {  # Part 0 "load by task" routing
    ("color", "colour", "grade", "grading", "lut", "scopes", "skin", "match", "matching"): ("Part 1", "Part 5", "Part 6", "Part 9", "K7"),
    ("cut", "trim", "ripple", "roll", "slip", "slide", "razor"): ("K2",),
    ("mask", "blend", "key", "keying", "transform", "composite", "layer"): ("K3",),
    ("effect", "keyframe", "transition", "speed", "reverse", "freeze"): ("K4",),
    ("audio", "dialogue", "music", "loudness", "eq", "ducking", "sync"): ("K5",),
    ("title", "subtitle", "subtitles", "logo", "lower"): ("K6",),
    ("proxy", "proxies", "import", "relink", "bin", "archive", "cache"): ("K8",),
    ("render", "export", "preset", "delivery"): ("K9",),
    ("shortcut", "shortcuts", "layout", "workspace", "panel"): ("K10",),
}


@dataclass
class Section:
    title: str
    text: str


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.casefold()) if t not in _STOP and len(t) > 1]


class KnowledgeBase:
    def __init__(self, path: Path):
        self.sections: list[Section] = []
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("knowledge base unavailable: %s", exc); return
        title, buf = "Introduction", []
        for line in raw.splitlines():
            if _HEAD.match(line.strip()):
                if "".join(buf).strip():
                    self.sections.append(Section(title, "\n".join(buf).strip()))
                title, buf = line.strip(), []
            else:
                buf.append(line)
        if "".join(buf).strip():
            self.sections.append(Section(title, "\n".join(buf).strip()))
        self.sections = [s for s in self.sections if len(s.text) > 80]
        self._tf = [_tokens(s.title + " " + s.title + " " + s.text) for s in self.sections]
        n = len(self._tf) or 1
        df: dict[str, int] = {}
        for toks in self._tf:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log(1 + n / d) for t, d in df.items()}
        self._avg = sum(map(len, self._tf)) / n if self._tf else 1

    def search(self, query: str, k: int = 3) -> list[Section]:
        q = _tokens(query)
        if not q or not self.sections:
            return []
        boost = set()
        for words, prefixes in _TOPIC_BOOST.items():
            if any(w in q for w in words):
                boost.update(prefixes)
        scores = []
        for sec, toks in zip(self.sections, self._tf):
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            s = 0.0
            for t in q:
                f = counts.get(t, 0)
                if f:
                    s += self._idf.get(t, 0) * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(toks) / self._avg))
            if s and any(sec.title.startswith(p + ":") or sec.title.startswith(p + ".") for p in boost):
                s *= 1.35
            scores.append((s, sec))
        return [sec for s, sec in sorted(scores, key=lambda x: -x[0])[:k] if s > 0]

    def answer(self, query: str, cfg: dict | None = None, ask=None) -> dict:
        hits = self.search(query)
        if not hits:
            return {"summary": f"No section of the reference covers “{query}”.", "sections": []}
        result = {"summary": "From the bundled reference (confirm every menu name and shortcut on screen before use):",
                  "sections": [{"title": s.title, "text": s.text[:2500]} for s in hits]}
        if ask is not None:
            context = "\n\n".join(f"## {s.title}\n{s.text[:3000]}" for s in hits)
            system = ("Answer the video editor's question using ONLY the reference text below. Be concise (max 8 steps). "
                      "Say that menu names and shortcuts must be confirmed on screen. If the text does not cover it, say so.\n\n" + context)
            try:
                result["answer"] = ask(cfg, query, system).strip()
            except Exception as exc:  # optional
                log.info("knowledge summarisation unavailable: %s", exc)
        return result
