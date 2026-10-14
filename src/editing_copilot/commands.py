"""Small, deterministic editing command language.

Parsing creates a proposal only. It never executes code, sends input, or edits a
project. Creative grading and guessed targets are deliberately unsupported.
"""

from dataclasses import dataclass
import json
import re
from typing import Any


MAX_FRAME = 2**31 - 1
MAX_COMMAND_LENGTH = 2048
MAX_NAME_LENGTH = 256
MARKER_COLORS = ("Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia", "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream")
_COLORS = {color.casefold(): color for color in MARKER_COLORS}
_CLIP = r"(?P<clip_id>[A-Za-z0-9_.:|{}\-]{1,256})"
_NUMBER = r"(?P<frame>[+-]?[0-9]+)"


class UnsupportedCommand(ValueError):
    """An unsupported, ambiguous, or invalid command; nothing was executed."""


@dataclass(frozen=True)
class Command:
    operation: str
    args: dict[str, Any]
    requires_target: bool = False


def _integer(text: str, *, positive: bool = False) -> int:
    # Guard before int conversion (and its implementation-specific digit limit).
    if len(text.lstrip("+-")) > 10:
        raise UnsupportedCommand(f"Frame values must be between {'1' if positive else '0'} and {MAX_FRAME}.")
    value = int(text)
    if value < (1 if positive else 0) or value > MAX_FRAME:
        raise UnsupportedCommand(f"Frame values must be between {'1' if positive else '0'} and {MAX_FRAME}.")
    return value


def _name_and_color(tail: str, allow_color: bool) -> tuple[str, str | None]:
    color = None
    if tail.startswith('"'):
        try:
            name, end = json.JSONDecoder().raw_decode(tail)
        except (ValueError, json.JSONDecodeError) as exc:
            raise UnsupportedCommand('Use a complete quoted name, for example named "Scene A".') from exc
        remainder = tail[end:].strip()
        if not isinstance(name, str):
            raise UnsupportedCommand("The marker or guide name must be text.")
        if remainder:
            match = re.fullmatch(r"color\s+([^\s]+)", remainder, re.IGNORECASE) if allow_color else None
            if not match:
                raise UnsupportedCommand("Unexpected text after the quoted name.")
            color = match.group(1)
    else:
        name = tail
        if allow_color:
            match = re.search(r"\s+color\s+([^\s]+)$", tail, re.IGNORECASE)
            if match:
                name = tail[:match.start()]
                color = match.group(1)
        if '"' in name:
            raise UnsupportedCommand("Put the complete name inside double quotes.")
    name = name.strip()
    if not name or len(name) > MAX_NAME_LENGTH or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise UnsupportedCommand(f"Names must contain 1 to {MAX_NAME_LENGTH} printable characters.")
    if color is not None:
        normalized = _COLORS.get(color.casefold())
        if normalized is None:
            raise UnsupportedCommand("Unsupported marker color. Use a documented Resolve color such as Blue, Green, Yellow, or Red.")
        color = normalized
    return name, color


def parse_command(text: str) -> Command:
    """Parse explicit English commands without inferring selection or intent.

    Frames are zero-based timeline frames. ``trim ... end by N frames`` shortens
    the selected instance's end without ripple; editor adapters must validate
    its source range, speed, and supported operation before execution. Names and
    clip IDs retain their original case. A literal suffix ``color Green`` sets
    a marker color; quote the name if that suffix belongs to the name itself.
    """
    if not isinstance(text, str):
        raise UnsupportedCommand("Enter a text command.")
    text = text.strip()
    if not text or len(text) > MAX_COMMAND_LENGTH:
        raise UnsupportedCommand(f"Enter a command of at most {MAX_COMMAND_LENGTH} characters.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise UnsupportedCommand("Enter one command on one line.")

    lowered = text.casefold()
    if lowered in ("inspect", "inspect project", "inspect timeline", "describe", "describe project"):
        return Command("inspect", {})
    if lowered in ("list clips", "list timeline clips"):
        return Command("list_clips", {})
    if lowered in ("undo", "stop"):
        return Command(lowered, {})
    if lowered == "export report":
        return Command("export_report", {})
    if lowered in ("inspect project details", "inspect details", "project details", "show project details"):
        return Command("inspect_details", {})
    if lowered in ("check media", "check media health", "media health", "media check", "check project media"):
        return Command("media_health", {})

    match = re.fullmatch(r"add\s+(?P<kind>marker|guide)\s+at\s+frame\s+" + _NUMBER + r"\s+named\s+(?P<tail>.+)", text, re.IGNORECASE)
    if match:
        kind = match.group("kind").casefold()
        frame = _integer(match.group("frame"))
        name, color = _name_and_color(match.group("tail"), allow_color=kind == "marker")
        args: dict[str, Any] = {"frame": frame, "name": name}
        if kind == "marker":
            args["color"] = color or "Green"
        return Command("add_" + kind, args)

    match = re.fullmatch(r"split\s+clip\s+" + _CLIP + r"\s+at\s+frame\s+" + _NUMBER, text, re.IGNORECASE)
    if match:
        return Command("split_clip", {"clip_id": match.group("clip_id"), "frame": _integer(match.group("frame"))}, True)

    match = re.fullmatch(r"trim\s+clip\s+" + _CLIP + r"\s+end\s+by\s+(?P<amount>[+-]?[0-9]+)\s+frames?", text, re.IGNORECASE)
    if match:
        return Command("trim_clip", {"clip_id": match.group("clip_id"), "edge": "end", "delta_frames": -_integer(match.group("amount"), positive=True), "ripple": False}, True)

    match = re.fullmatch(r"(?:add|apply)\s+(?:the\s+)?effect\s+(?P<name>.+?)\s+to\s+clip\s+" + _CLIP, text, re.IGNORECASE)
    if match:
        effect = match.group("name").strip().strip('"').strip()
        if not effect or len(effect) > 64 or any(ord(ch) < 32 for ch in effect):
            raise UnsupportedCommand("Name one effect from the safe list.")
        return Command("add_effect", {"effect": effect, "clip_id": match.group("clip_id")}, True)

    match = re.fullmatch(r"(?P<state>mute|unmute|lock|unlock|hide|unhide|show)\s+track\s+(?P<track>.+)", text, re.IGNORECASE)
    if match:
        track = match.group("track").strip()
        if len(track) >= 2 and track[0] == track[-1] == '"':
            track = track[1:-1].strip()
        if not track or len(track) > MAX_NAME_LENGTH or '"' in track:
            raise UnsupportedCommand('Name the track, for example: lock track "Video 1".')
        state = match.group("state").casefold()
        return Command("set_track", {"state": "unhide" if state == "show" else state, "track": track})

    match = re.fullmatch(r"move\s+clip\s+" + _CLIP + r"\s+to\s+frame\s+" + _NUMBER, text, re.IGNORECASE)
    if match:
        return Command("move_clip", {"clip_id": match.group("clip_id"), "frame": _integer(match.group("frame"))}, True)

    match = re.fullmatch(r"(?:delete|remove)\s+clip\s+" + _CLIP, text, re.IGNORECASE)
    if match:
        return Command("delete_clip", {"clip_id": match.group("clip_id")}, True)

    if re.search(r"\b(color|colour|grade|grading|dramatic|cinematic|brighter|exposure|match)\b", text, re.IGNORECASE):
        raise UnsupportedCommand("Creative color and shot matching are not implemented in this release. No change was made. Use an explicit supported timeline command.")
    raise UnsupportedCommand('Unsupported or ambiguous command. Use: inspect; inspect project details; check media; list clips; add marker at frame N named "Name"; add guide at frame N named "Name"; split clip ID at frame N; trim clip ID end by N frames; add effect NAME to clip ID; lock/unlock/mute/unmute/hide/show track NAME; move clip ID to frame N; delete clip ID; undo; stop.')
