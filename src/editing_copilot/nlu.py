"""Turn spoken / casual English into the canonical command grammar.

The output is always either a *control* word (preview, apply, cancel, stop,
undo), a *live* editor shortcut action, or a canonical text command that is
then validated by :func:`commands.parse_command`. Nothing here executes edits.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .commands import UnsupportedCommand, parse_command

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_UNITS.update({"oh": 0, "a": 1, "an": 1})
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_SCALES = {"hundred": 100, "thousand": 1000}
_NUMWORDS = set(_UNITS) | set(_TENS) | set(_SCALES) | {"and"}

CONTROL = {
    "preview": "preview", "check": "preview", "check it": "preview", "show me": "preview",
    "apply": "apply", "confirm": "confirm", "yes": "confirm", "yes confirm": "confirm", "do it": "apply", "yes apply": "apply", "go ahead": "apply",
    "cancel": "cancel", "never mind": "cancel", "nevermind": "cancel", "forget it": "cancel",
    "stop": "stop", "halt": "stop", "abort": "stop",
    "undo": "undo", "undo that": "undo", "undo last edit": "undo",
    "inspect": "inspect", "refresh": "inspect", "reload": "inspect",
}

LIVE_PATTERNS = [
    (r"(play|resume|start playback)", "play"),
    (r"(pause|stop playback)", "pause"),
    (r"(redo)", "redo"),
    (r"(save|save project)", "save"),
    (r"(cut|razor|blade|split)( (it|here|at (the )?playhead))?( now)?", "cut"),
    (r"(add |drop |put )?(a )?guide( here| at (the )?playhead)?", "guide"),
    (r"(add |drop |put )?(a )?marker( here| at (the )?playhead)?", "marker"),
    (r"(go to |jump to )?(the )?(start|beginning)", "start"),
    (r"(go to |jump to )?(the )?end", "end"),
    (r"(next|forward one) frame", "next frame"),
    (r"(previous|back one|last) frame", "previous frame"),
    (r"(set |mark )?in( point)?", "in point"),
    (r"(set |mark )?out( point)?", "out point"),
    (r"(delete|remove) (it|clip|selection|selected clip)", "delete"),
    (r"render", "render"),
    (r"zoom in", "zoom in"),
    (r"zoom out", "zoom out"),
]


@dataclass(frozen=True)
class Intent:
    kind: str          # control | command | live | ui | macro | help | unknown
    value: str         # control word, canonical command text, or live action name
    source: str = ""   # original utterance
    data: object = None  # ui: list[Action] ; macro: (verb, name) ; help: query


def words_to_numbers(text: str) -> str:
    """'frame two hundred and five' -> 'frame 205'. Leaves other words intact."""
    tokens = re.split(r"(\s+|-)", text)
    out, total, current, active = [], 0, 0, False

    def flush():
        nonlocal total, current, active
        if active:
            out.append(str(total + current))
        total = current = 0
        active = False

    pending_space = []
    for tok in tokens:
        low = tok.casefold()
        if tok.strip() == "" or tok == "-":
            (pending_space if active else out).append(tok if tok != "-" or not active else "")
            continue
        if low in _NUMWORDS and not (low in ("a", "an", "and", "oh") and not active and low != "oh"):
            if low == "and":
                if not active:
                    out.extend(pending_space); pending_space = []; out.append(tok)
                continue
            pending_space = []
            active = True
            if low in _UNITS:
                current += _UNITS[low]
            elif low in _TENS:
                current += _TENS[low]
            elif low == "hundred":
                current = max(current, 1) * 100
            else:
                total += max(current, 1) * 1000
                current = 0
            continue
        flush()
        out.extend(pending_space); pending_space = []
        out.append(tok)
    flush()
    out.extend(pending_space)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def strip_wake_word(text: str, wake_word: str, required: bool) -> str | None:
    text = text.strip()
    if not wake_word:
        return text
    m = re.match(r"^\s*(hey |ok |okay )?" + re.escape(wake_word.casefold()) + r"\b[\s,.:!]*", text.casefold())
    if m:
        return text[m.end():].strip()
    return None if required else text


def _frames(value: str, unit: str | None, fps: float) -> int:
    if unit and unit.startswith("sec"):
        return round(float(value) * fps)
    return int(float(value))


def normalize(text: str, fps: float = 25.0) -> str:
    """Rewrite casual phrasing into canonical command text (best effort)."""
    t = words_to_numbers(text.strip().rstrip(".!?")).strip()
    t = re.sub(r"^(please |can you |could you |copilot )+", "", t, flags=re.I)
    t = re.sub(r"\s+please$", "", t, flags=re.I)
    # timecode hh:mm:ss:ff -> frames
    def tc(m):
        h, mi, s, f = (int(x) for x in m.groups())
        return f"frame {round(((h * 60 + mi) * 60 + s) * fps) + f}"
    t = re.sub(r"(?:at\s+)?(?:timecode\s+)?\b(\d{1,2}):(\d{2}):(\d{2})[:;](\d{2})\b", lambda m: "at " + tc(m), t)
    # "at 3 seconds" / "at second 3" -> frames
    t = re.sub(r"\bat\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?)\b", lambda m: f"at frame {_frames(m.group(1), 'sec', fps)}", t, flags=re.I)
    t = re.sub(r"\bat\s+second\s+(\d+(?:\.\d+)?)\b", lambda m: f"at frame {_frames(m.group(1), 'sec', fps)}", t, flags=re.I)
    t = re.sub(r"\bat\s+(\d+)\b(?!\s*frames?)", r"at frame \1", t, flags=re.I)  # "at 25" -> frame
    t = re.sub(r"\bat\s+frame\s+frame\b", "at frame", t, flags=re.I)
    # marker / guide synonyms
    t = re.sub(r"^(put|drop|place|insert|create|set)\s+(a\s+|an\s+)?", "add ", t, flags=re.I)
    # frequent small-model mishearings of "add"
    t = re.sub(r"^(and|at|out|had|odd|ad|i'd)\s+(?=(a\s+|an\s+)?(marker|guide)\b)", "add ", t, flags=re.I)
    t = re.sub(r"^add\s+(a\s+|an\s+)", "add ", t, flags=re.I)
    t = re.sub(r"\b(called|labelled|labeled|titled|saying)\b", "named", t, flags=re.I)
    # clip edits
    t = re.sub(r"^(cut|razor|blade)\b", "split", t, flags=re.I)
    t = re.sub(r"^split\s+(the\s+)?(selected\s+clip|selection|this\s+clip|clip)\b", "split clip selected", t, flags=re.I)
    t = re.sub(r"^(shorten|trim)\s+(the\s+)?(selected\s+clip|selection|this\s+clip|clip)\s+(end\s+)?by\b", "trim clip selected end by", t, flags=re.I)
    t = re.sub(r"\bend by (\d+)$", r"end by \1 frames", t, flags=re.I)
    t = re.sub(r"\bcolou?r\s+(\w+)$", lambda m: "color " + m.group(1).capitalize(), t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


_ROLE_WORDS = {"button": "button", "tab": "tab", "menu": "menu", "field": "field", "box": "field",
               "checkbox": "checkbox", "panel": "panel", "item": "item", "slider": "slider", "page": "tab"}
_KEY_WORDS = {"enter": "return", "return": "return", "escape": "escape", "esc": "escape", "tab": "tab",
              "space": "space", "delete": "delete", "control": "ctrl", "ctrl": "ctrl", "shift": "shift",
              "alt": "alt", "plus": "plus", "minus": "minus", "up": "up", "down": "down", "left": "left",
              "right": "right", "home": "home", "end": "end", "backslash": "backslash", "backspace": "backspace", "windows": "win", "win": "win",
              "page": "page", "insert": "insert", "comma": "comma", "period": "period", "dot": "period"}


def spoken_key(text: str) -> str:
    """'control shift z' / 'ctrl+s' / 'F5' -> 'ctrl+shift+z'."""
    parts = [p for p in re.split(r"[\s+]+", text.casefold().strip()) if p and p not in ("and", "the", "key")]
    return "+".join(_KEY_WORDS.get(p, p) for p in parts)


def parse_ui(raw: str) -> Intent | None:
    from .actions import Action
    text = words_to_numbers(raw.strip().rstrip(".!?"))
    low = text.casefold()
    m = re.fullmatch(r"record (?:a )?macro (?:called |named )?(.+)", low)
    if m:
        return Intent("macro", "record", raw, ("record", m.group(1).strip()))
    if re.fullmatch(r"(stop|end|finish|save) recording( macro)?", low):
        return Intent("macro", "stop_recording", raw, ("stop_recording", ""))
    m = re.fullmatch(r"(?:run|play|do|start) macro (.+)", low)
    if m:
        return Intent("macro", "run", raw, ("run", m.group(1).strip()))
    if re.fullmatch(r"(list|show)( my)? macros", low):
        return Intent("macro", "list", raw, ("list", ""))
    m = re.fullmatch(r"(how do i|how to|how can i|explain|what is|what's|help( me)? with|tell me about) (.+)", low)
    if m:
        return Intent("help", m.group(3).strip(), raw, m.group(3).strip())
    mods = ""
    mm = re.match(r"(?:hold )?((?:(?:ctrl|control|shift|alt)[ +-]?)+)(?=(?:double |right )?click|drag)", low)
    if mm:
        mods = spoken_key(mm.group(1))
        text = text[mm.end():].strip()
        low = text.casefold()
    index = 1
    om = re.search(r"\b(?:the )?(first|second|third|fourth|fifth|last)\b ", low)
    if om and re.match(r"(double |right )?(click|select|drag|press)", low):
        index = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": 1}[om.group(1)]
        text = text[:om.start()] + text[om.end():]
        low = text.casefold()
    m = re.fullmatch(r"drag (?:from )?(\d+)[ ,x]+(\d+) to (\d+)[ ,x]+(\d+)", low)
    if m:
        a = Action("drag", x=int(m.group(1)), y=int(m.group(2)), x2=int(m.group(3)), y2=int(m.group(4)), modifiers=mods)
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"drag (?:the )?(.+?) (left|right|up|down) (?:by )?(\d+)(?: pixels?| px)?", text, re.I)
    if m:
        n = int(m.group(3)); d = m.group(2).casefold()
        a = Action("drag", label=m.group(1), dx=n if d == "right" else -n if d == "left" else 0,
                   dy=n if d == "down" else -n if d == "up" else 0, modifiers=mods, index=index)
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"(?:drag|move|drop) (?:the )?(.+?) (?:to|onto|into|on) (?:the )?(.+)", text, re.I)
    if m and not re.match(r"(?:mouse|cursor|pointer)\b", m.group(1), re.I):
        a = Action("drag", label=m.group(1).strip(), to_label=m.group(2).strip(), modifiers=mods, index=index)
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"(?:move (?:the )?(?:mouse|cursor|pointer) to|hover(?: over| on)?|point at) (?:the )?(.+)", text, re.I)
    if m:
        c = re.fullmatch(r"(\d+)[ ,x]+(\d+)", m.group(1).strip())
        a = Action("move", x=int(c.group(1)), y=int(c.group(2))) if c else Action("move", label=m.group(1).strip())
        return Intent("ui", a.describe(), raw, [a])
    if re.fullmatch(r"(close|dismiss) (the )?(dialog|popup|window|menu)", low):
        a = Action("key", text="escape")
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"(double[ -]?|right[ -]?|middle[ -]?)?click at (\d+)[ ,x]+(?:and )?(\d+)", low)
    if m:
        kind = (m.group(1) or "").replace("-", "").strip()
        a = Action("click_at", x=int(m.group(2)), y=int(m.group(3)), button="right" if kind == "right" else "middle" if kind == "middle" else "left", double=kind == "double", modifiers=mods)
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"(double[ -]?|right[ -]?)?(?:click|press|tap|select|hit|choose)(?: on)? (?:the )?(.+?)(?: (button|tab|menu|field|box|checkbox|panel|item|slider|page))?", text, re.I)
    if m and not re.fullmatch(r"(press|hit)\s.+", low):
        kind = (m.group(1) or "").replace("-", "").strip().casefold()
        a = Action("click", label=m.group(2).strip(" \"'"), role=_ROLE_WORDS.get((m.group(3) or "").casefold(), ""),
                   button="right" if kind == "right" else "left", double=kind == "double", modifiers=mods, index=index)
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"open (?:the )?(.+?) (menu|tab|panel)", text, re.I)
    if m:
        a = Action("click", label=m.group(1).strip(), role=_ROLE_WORDS[m.group(2).casefold()])
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"(?:go to|switch to|show) (?:the )?(.+?) (tab|page|panel)", text, re.I)
    if m:
        a = Action("click", label=m.group(1).strip(), role="tab")
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"type (.+)", text, re.I)
    if m:
        a = Action("type", text=m.group(1).strip().strip('"'))
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"(?:press|hit) (?:the )?(.+?)(?: key)?", text, re.I)
    if m:
        a = Action("key", text=spoken_key(m.group(1)))
        try:
            a.validate()
        except Exception:
            return None
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"scroll (up|down)(?: (\d+))?(?: times)?", low)
    if m:
        n = int(m.group(2) or 3)
        a = Action("scroll", notches=n if m.group(1) == "up" else -n)
        return Intent("ui", a.describe(), raw, [a])
    m = re.fullmatch(r"wait (\d+(?:\.\d+)?) ?(?:seconds?|secs?)?", low)
    if m:
        a = Action("wait", seconds=min(30.0, float(m.group(1))))
        return Intent("ui", a.describe(), raw, [a])
    return None


def interpret(utterance: str, fps: float = 25.0, editor: str = "kdenlive") -> Intent:
    """Rule-based interpretation; returns Intent(kind='unknown') if nothing safe matched."""
    raw = utterance.strip()
    low = re.sub(r"[^\w\s:'\"-]", "", raw.casefold()).strip()
    low = re.sub(r"^(please |copilot )+", "", low)
    if low in CONTROL:
        return Intent("control", CONTROL[low], raw)
    from .workflows import is_destructive, match as workflow_match
    flow = workflow_match(raw, editor)
    if flow is not None:
        return Intent("workflow", flow[0], raw, (flow[1], is_destructive(flow[0])))
    ui = parse_ui(re.sub(r"^(please |copilot )+", "", raw, flags=re.I))
    if ui is not None:
        return ui
    for pattern, action in LIVE_PATTERNS:
        if re.fullmatch(pattern, low):
            if action in ("guide", "marker"):
                action = "guide" if editor == "kdenlive" else "marker"
            return Intent("live", action, raw)
    canonical = normalize(raw, fps)
    try:
        parse_command(canonical)
    except UnsupportedCommand:
        return Intent("unknown", canonical, raw)
    return Intent("command", canonical, raw)
