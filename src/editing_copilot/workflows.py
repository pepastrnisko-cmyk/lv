"""Expert voice workflows built from the click/type engine.

Names, menus and shortcuts follow the bundled master reference (K2-K10) and the
editors' default layouts. The reference says "never assume a name": each step
locates its label on screen (UIA, then OCR) and the run stops - without
guessing - the moment a label is missing. Destructive workflows (render,
project settings, reset grade) are confirmed by voice first via Executor.
"""
from __future__ import annotations

import re

from .actions import Action


def A(kind, **kw):
    return Action(kind, **kw)


# Resolve default page shortcuts (Shift+2..8) and Color-page node keys.
RESOLVE_PAGES = {"media": "shift+2", "cut": "shift+3", "edit": "shift+4", "fusion": "shift+5",
                 "color": "shift+6", "colour": "shift+6", "fairlight": "shift+7", "deliver": "shift+8"}
RESOLVE_NODES = {"serial": "alt+s", "parallel": "alt+p", "layer": "alt+l", "outside": "alt+o"}
KDENLIVE_WORKSPACES = ("logging", "editing", "audio", "effects", "color")
KDENLIVE_SCOPES = {"waveform": "Waveform", "vectorscope": "Vectorscope", "histogram": "Histogram",
                   "rgb parade": "RGB Parade", "parade": "RGB Parade", "audio spectrum": "Audio Spectrum"}
KDENLIVE_PANELS = {"effects": "Effects", "compositions": "Compositions", "transitions": "Compositions",
                   "project bin": "Project Bin", "bin": "Project Bin", "effect stack": "Effect/Composition Stack",
                   "properties": "Effect/Composition Stack", "audio mixer": "Audio Mixer", "mixer": "Audio Mixer",
                   "subtitles": "Subtitles", "library": "Library", "clip monitor": "Clip Monitor",
                   "project monitor": "Project Monitor", "undo history": "Undo History", "titles": "Titles"}


def kdenlive_add_from_panel(panel_tab: str, name: str) -> list[Action]:
    """Kdenlive: search the Effects/Compositions list and apply to the selected timeline clip.
    Double-clicking a list entry applies it to the selected clip (select the clip first)."""
    return [A("click", label=panel_tab, role="tab"), A("wait", seconds=0.3),
            A("click", label="Search", role="field"), A("key", text="ctrl+a"), A("type", text=name),
            A("wait", seconds=1.5), A("click", label=name, role="item", double=True)]


def match(text: str, editor: str) -> tuple[str, list[Action]] | None:
    low = re.sub(r"[^\w\s+-]", "", text.casefold()).strip()
    low = re.sub(r"^(please |copilot )+", "", low)
    if editor == "kdenlive":
        m = re.fullmatch(r"(?:add|apply) (?:the )?(?:effect )?(.+?)(?: effect)?(?: to (?:the )?(?:selected )?clip)?", low)
        if m and not re.match(r"(marker|guide|a marker|a guide)\b", m.group(1)) and " at frame" not in low:
            name = m.group(1)
            if re.fullmatch(r"(?:a )?(?:transition|composition|wipe|dissolve|fade)(?: .*)?", name) or "transition" in low or "composition" in low:
                name = re.sub(r"^(a |the )?(transition|composition) ?", "", name).strip() or "Dissolve"
                return f"add composition “{name}”", kdenlive_add_from_panel("Compositions", name)
            return f"add effect “{name}”", kdenlive_add_from_panel("Effects", name)
        m = re.fullmatch(r"(?:add|apply) (?:a )?(?:transition|composition) (.+)", low)
        if m:
            return f"add composition “{m.group(1)}”", kdenlive_add_from_panel("Compositions", m.group(1))
        m = re.fullmatch(r"(?:switch to|open|go to|show) (?:the )?(logging|editing|audio|effects|color|colour) (?:workspace|layout)", low)
        if m:
            ws = "color" if m.group(1) == "colour" else m.group(1)
            return f"{ws} workspace", [A("click", label=ws.title(), role="tab")]
        m = re.fullmatch(r"(?:open|show) (?:the )?(waveform|vectorscope|histogram|rgb parade|parade|audio spectrum)(?: scope)?", low)
        if m:
            return f"show {KDENLIVE_SCOPES[m.group(1)]}", [A("click", label="View", role="menu"), A("wait", seconds=0.3),
                                                           A("click", label=KDENLIVE_SCOPES[m.group(1)], role="menu")]
        if re.fullmatch(r"(?:open|show) (?:the )?(?:color|colour) tools|(?:open|show) (?:the )?scopes", low):
            return "color workspace + scopes", [A("click", label="Color", role="tab")]
        m = re.fullmatch(r"(?:open|show) (?:the )?(" + "|".join(sorted(KDENLIVE_PANELS, key=len, reverse=True)) + r")(?: panel)?", low)
        if m:
            return f"show {KDENLIVE_PANELS[m.group(1)]}", [A("click", label="View", role="menu"), A("wait", seconds=0.3),
                                                           A("click", label=KDENLIVE_PANELS[m.group(1)], role="menu")]
        m = re.fullmatch(r"(?:open (?:the )?render(?: dialog| window)?|render)(?: with (?:preset )?(.+))?", low)
        if m:
            # Kdenlive 25+/26 has a Render toolbar button; older builds have Project > Render
            steps = [A("click", label="Render", role="button"), A("wait", seconds=1.2)]
            if m.group(1):
                steps.append(A("click", label=m.group(1), role="item"))
            return "open render dialog" + (f", preset “{m.group(1)}”" if m.group(1) else "") + " (does not start rendering)", steps
        if re.fullmatch(r"(?:open )?project settings", low):
            return "open project settings", [A("click", label="Project|Sequence|Settings", role="menu"), A("wait", seconds=0.4), A("click", label="Project Settings", role="menu")]
        if re.fullmatch(r"(?:add|create) (?:a )?title(?: clip)?", low):
            return "add title clip", [A("click", label="Media|Project", role="menu"), A("wait", seconds=0.4), A("click", label="Add Title Clip|Create Title", role="menu")]
        if re.fullmatch(r"(?:open )?(?:keyboard )?shortcuts?(?: settings)?|configure shortcuts", low):
            return "shortcut editor", [A("click", label="Settings", role="menu"), A("wait", seconds=0.3), A("click", label="Configure Keyboard Shortcuts", role="menu")]
        if re.fullmatch(r"(?:open )?(?:help )?about(?: kdenlive)?|which version", low):
            return "Help > About (check version, per reference K1)", [A("click", label="Help", role="menu"), A("wait", seconds=0.3), A("click", label="About Kdenlive", role="menu")]
        if re.fullmatch(r"(?:select )?(?:the )?razor tool|razor", low):
            return "razor tool", [A("key", text="x")]
        if re.fullmatch(r"(?:select )?(?:the )?selection tool|selection", low):
            return "selection tool", [A("key", text="s")]
        if re.fullmatch(r"(?:select all|select everything)", low):
            return "select all", [A("key", text="ctrl+a")]
        if re.fullmatch(r"(?:add|insert) (?:a )?(?:video |audio )?track", low):
            return "insert track", [A("click", label="Sequence|Timeline", role="menu"), A("wait", seconds=0.4), A("click", label="Tracks", role="menu"),
                                    A("wait", seconds=0.4), A("click", label="Insert Track", role="menu")]
    else:  # resolve
        m = re.fullmatch(r"(?:switch to|go to|open|show) (?:the )?(media|cut|edit|fusion|color|colour|fairlight|deliver)(?: page| tab)?", low)
        if m:
            return f"{m.group(1)} page", [A("key", text=RESOLVE_PAGES[m.group(1)])]
        m = re.fullmatch(r"(?:add|create|new) (?:a )?(serial|parallel|layer|outside) node", low)
        if m:
            return f"add {m.group(1)} node", [A("key", text=RESOLVE_PAGES["color"]), A("wait", seconds=0.6), A("key", text=RESOLVE_NODES[m.group(1)])]
        if re.fullmatch(r"(?:add|create|new) (?:a )?node", low):
            return "add serial node", [A("key", text=RESOLVE_PAGES["color"]), A("wait", seconds=0.6), A("key", text="alt+s")]
        if re.fullmatch(r"(?:show|open|toggle) (?:the )?scopes|(?:show|open) (?:the )?(?:waveform|vectorscope|parade)", low):
            return "toggle scopes", [A("key", text="ctrl+shift+w")]
        if re.fullmatch(r"(?:grab|grab a|take a) still", low):
            return "grab still", [A("key", text="ctrl+alt+g")]
        if re.fullmatch(r"(?:toggle )?bypass (?:all )?(?:grades|nodes|color)", low):
            return "bypass grades", [A("key", text="shift+d")]
        if re.fullmatch(r"(?:reset|remove|clear) (?:the )?grade|reset all grades", low):
            return "reset grade (destructive)", [A("click", label="Color", role="menu"), A("wait", seconds=0.3), A("click", label="Reset All Grades and Nodes", role="menu")]
        if re.fullmatch(r"(?:open )?project settings", low):
            return "project settings", [A("key", text="shift+9")]
        if re.fullmatch(r"(?:add to )?render queue|(?:open )?deliver(?: page)?(?: with (?:preset )?(.+))?", low):
            return "deliver page (no render started)", [A("key", text=RESOLVE_PAGES["deliver"])]
        m = re.fullmatch(r"(?:render|deliver) (?:with |using )?(?:preset )?(.+)", low)
        if m:
            return f"deliver page, preset “{m.group(1)}”", [A("key", text=RESOLVE_PAGES["deliver"]), A("wait", seconds=1.0), A("click", label=m.group(1))]
        if re.fullmatch(r"(?:select )?(?:the )?blade tool|blade", low):
            return "blade tool", [A("key", text="b")]
        if re.fullmatch(r"(?:select )?(?:the )?selection tool|selection", low):
            return "selection tool", [A("key", text="a")]
    return None


DESTRUCTIVE_WORKFLOWS = ("render", "reset grade", "project settings", "preset")


def is_destructive(description: str) -> bool:
    return any(w in description for w in DESTRUCTIVE_WORKFLOWS)


CHEATSHEET = """WHAT CAN I SAY  (start with the wake word, e.g. “copilot …”)

CONTROL      preview · apply / confirm · cancel · undo · inspect · stop
PLAYBACK     play · pause · go to start/end · next/previous frame · set in point · set out point
EDITING      cut / razor here · guide here · marker here · save · redo · delete clip (confirms)
PROJECT EDIT add guide at 10 seconds named Intro · add marker at frame 250 named Hook colour red
             cut the selected clip at frame 300 · shorten the selected clip by 5
MOUSE        click Render · click the Edit tab · open File menu · double click Intro · right click Intro
             shift click Outro · click the second Interview · click at 640 480 · hover over Effects
DRAG         drag Intro to Video 2 · drag Intro right 120 pixels · drag from 400 600 to 900 600
KEYBOARD     type Final cut · press enter · press control shift z · press F5 · close dialog · scroll down 3
MACROS       record macro my export … stop recording · run macro my export · list macros
HELP         how do I match skin tones · explain ripple trim · how do I set up proxies

KDENLIVE     add effect Gaussian blur · add transition Dissolve · switch to color workspace
             open vectorscope · open effects panel · open render dialog (with preset H264) · project settings
             add title · insert track · razor tool · selection tool · which version
RESOLVE      go to color page / edit / cut / fusion / fairlight / deliver · add serial / parallel / layer node
             show scopes · grab still · bypass grades · reset grade (confirms) · render with preset YouTube
             blade tool · selection tool

Destructive actions (delete, render, overwrite, project settings, reset…) always wait for “confirm”.
Emergency stop: Ctrl+Shift+Space or say “stop”.
"""
