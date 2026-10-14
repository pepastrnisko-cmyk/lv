"""Extended Kdenlive project-copy edits: allowlisted effects, track state, move and delete clip.

Each operation has three parts used by ``KdenliveProject``: ``plan_*`` validates
against the parsed source project and returns canonical args plus a summary;
``apply_*`` mutates a deep copy of the XML tree; ``verify_*`` re-reads the
written temporary copy from disk and checks the exact intended result. The
original project file is never written.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

EXTENDED_OPERATIONS = ("add_effect", "set_track", "move_clip", "delete_clip")
DESTRUCTIVE_OPERATIONS = frozenset({"delete_clip"})

# Allowlist: spoken name -> (MLT service, Kdenlive effect id, fixed safe parameters).
# Every service was confirmed present in the local MLT build (``melt -query filters``).
EFFECTS: dict[str, tuple[str, str, dict[str, str]]] = {
    "greyscale": ("greyscale", "greyscale", {}),
    "sepia": ("sepia", "sepia", {"u": "75", "v": "150"}),
    "gaussian blur": ("avfilter.gblur", "avfilter.gblur", {"av.sigma": "4", "av.steps": "1"}),
    "box blur": ("avfilter.boxblur", "avfilter.boxblur", {"av.luma_radius": "4", "av.luma_power": "1"}),
    "brightness": ("brightness", "brightness", {"level": "1.2"}),
    "mirror": ("avfilter.hflip", "avfilter.hflip", {}),
    "invert": ("avfilter.negate", "avfilter.negate", {}),
}
EFFECT_ALIASES = {"grayscale": "greyscale", "black and white": "greyscale", "black & white": "greyscale",
                  "blur": "gaussian blur", "gblur": "gaussian blur", "brighten": "brightness",
                  "flip": "mirror", "horizontal flip": "mirror", "negative": "invert", "negate": "invert"}
TRACK_STATES = ("lock", "unlock", "mute", "unmute", "hide", "unhide")


def canonical_effect(name: str) -> str | None:
    key = " ".join(str(name).casefold().replace("-", " ").split())
    key = EFFECT_ALIASES.get(key, key)
    return key if key in EFFECTS else None


def _props(node):
    return {p.get("name"): (p.text or "") for p in node.findall("property")}


def _set_prop(node: ET.Element, name: str, value: str) -> None:
    props = node.findall("property")
    for child in props:
        if child.get("name") == name:
            child.text = value
            return
    new = ET.Element("property", {"name": name})
    new.text = value
    children = list(node)
    index = children.index(props[-1]) + 1 if props else 0
    node.insert(index, new)


def _hide_set(value: str | None) -> set[str]:
    return {"video", "audio"} if value == "both" else ({value} if value in ("video", "audio") else set())


def _hide_value(parts: set[str]) -> str | None:
    if parts == {"video", "audio"}:
        return "both"
    return next(iter(parts)) if parts else None


def _layout(project, playlist: ET.Element) -> list[tuple[int, int, ET.Element]]:
    """(timeline_in, length, entry) for every entry of a playlist."""
    rows, cursor = [], 0
    for node in playlist:
        if node.tag == "blank":
            cursor += project._frames(node.get("length"))
        elif node.tag == "entry":
            length = project._frames(node.get("out")) - project._frames(node.get("in")) + 1
            rows.append((cursor, length, node))
            cursor += length
    return rows


def _rebuild(playlist: ET.Element, placed: list[tuple[int, int, ET.Element]]) -> None:
    """Rewrite a playlist's entries/blanks from absolute positions; keep other children."""
    keep = [n for n in playlist if n.tag not in ("entry", "blank")]
    for node in list(playlist):
        playlist.remove(node)
    for node in keep:
        playlist.append(node)
    cursor = 0
    for start, length, entry in sorted(placed, key=lambda r: r[0]):
        if start < cursor:
            raise ValueError("overlap")
        if start > cursor:
            playlist.append(ET.Element("blank", {"length": str(start - cursor)}))
        playlist.append(entry)
        cursor = start + length


def _signature(entry: ET.Element) -> tuple:
    return (entry.get("producer"), entry.get("in"), entry.get("out"),
            tuple((p.get("name"), p.text) for p in entry.findall("property")),
            tuple(f.get("id") for f in entry.findall("filter")))


def _sequence_duration(project, sequence: ET.Element) -> int:
    best = 0
    for ref in sequence.findall("track"):
        track = project.elements.get(ref.get("producer", ""))
        if track is None or track.tag != "tractor":
            continue
        for lane in track.findall("track"):
            playlist = project.elements.get(lane.get("producer", ""))
            if playlist is not None and playlist.tag == "playlist":
                rows = _layout(project, playlist)
                if rows:
                    best = max(best, rows[-1][0] + rows[-1][1])
    return best


# ---------------------------------------------------------------- planning
def plan(project, operation: str, params: dict, error) -> tuple[dict, str]:
    if operation == "add_effect":
        if set(params) != {"instance_id", "effect"}:
            raise error("add_effect requires exactly: instance_id, effect.")
        effect = canonical_effect(params["effect"]) if isinstance(params["effect"], str) else None
        if effect is None:
            raise error("Effect is not on the safe list: " + ", ".join(sorted(EFFECTS)) + ".")
        item = project._instances.get(params["instance_id"]) if isinstance(params["instance_id"], str) else None
        if item is None:
            raise error("Unknown timeline instance; inspect the project again.")
        for node in (item["track"], item["playlist"]):
            if any(_props(node).get(k) == "1" for k in ("kdenlive:locked_track", "kdenlive:locked")):
                raise error("Target track is locked.")
        if item["producer"].tag not in ("producer", "chain"):
            raise error("Effects on nested sequences are unsupported.")
        service = EFFECTS[effect][0]
        if any(_props(f).get("mlt_service") == service for f in item["node"].findall("filter")):
            raise error(f"The clip already has the {effect} effect.")
        return {"instance_id": params["instance_id"], "effect": effect}, f"Add {effect} effect to {item['name']} (project copy)."
    if operation == "set_track":
        if set(params) - {"sequence_id"} != {"track_id", "state"}:
            raise error("set_track requires exactly: track_id, state.")
        state = params["state"]
        if state not in TRACK_STATES:
            raise error("Track state must be one of: " + ", ".join(TRACK_STATES) + ".")
        track_id = params["track_id"]
        refs = [(seq_id, ref) for seq_id, seq in project.sequences.items() for ref in seq.findall("track")
                if isinstance(track_id, str) and ref.get("producer") == track_id]
        track = project.elements.get(track_id) if isinstance(track_id, str) else None
        if track is None or track.tag != "tractor" or len(refs) != 1:
            raise error("Select one exact timeline track (inspect the project for track names).")
        if "sequence_id" in params and params["sequence_id"] != refs[0][0]:
            raise error("Track belongs to a different sequence; inspect again.")
        props = _props(track)
        audio = props.get("kdenlive:audio_track") == "1"
        name = props.get("kdenlive:track_name", track_id)
        if state in ("mute", "unmute") and not audio:
            raise error("Mute applies to audio tracks; use hide/unhide for video tracks.")
        if state in ("hide", "unhide") and audio:
            raise error("Hide applies to video tracks; use mute/unmute for audio tracks.")
        locked = props.get("kdenlive:locked_track") == "1"
        hidden = _hide_set(refs[0][1].get("hide"))
        current = {"lock": locked, "unlock": not locked, "mute": "audio" in hidden, "unmute": "audio" not in hidden,
                   "hide": "video" in hidden, "unhide": "video" not in hidden}[state]
        if current:
            done = {"lock": "locked", "unlock": "unlocked", "mute": "muted", "unmute": "unmuted",
                    "hide": "hidden", "unhide": "visible"}[state]
            raise error(f"Track {name} is already {done}; no change.")
        verb = {"lock": "Lock", "unlock": "Unlock", "mute": "Mute", "unmute": "Unmute", "hide": "Hide", "unhide": "Show"}[state]
        return {"track_id": track_id, "state": state, "sequence_id": refs[0][0]}, f"{verb} track {name} (project copy)."
    if operation in ("move_clip", "delete_clip"):
        expected = {"instance_id", "frame"} if operation == "move_clip" else {"instance_id"}
        if set(params) != expected:
            raise error(f"{operation} requires exactly: {', '.join(sorted(expected))}.")
        item = project._simple_instance(params["instance_id"])
        if operation == "delete_clip":
            return ({"instance_id": params["instance_id"]},
                    f"DELETE {item['name']} at frames [{item['timeline_in']}, {item['timeline_out_exclusive']}) and leave a gap "
                    "(no ripple; project copy, original untouched). Requires confirmation.")
        frame = params["frame"]
        if type(frame) is not int or frame < 0:
            raise error("Move target frame must be a non-negative integer.")
        if frame == item["timeline_in"]:
            raise error("The clip is already at that frame.")
        length = item["duration_frames"]
        others = [(s, n) for s, n, e in _layout(project, item["playlist"]) if e is not item["node"]]
        if any(s < frame + length and frame < s + n for s, n in others):
            raise error("Target range overlaps another clip on this track.")
        limit = _sequence_duration(project, item["sequence"])
        if frame + length > limit:
            raise error(f"Moving past the end of the sequence (frame {limit}) is unsupported.")
        return ({"instance_id": params["instance_id"], "frame": frame},
                f"Move {item['name']} from frame {item['timeline_in']} to frame {frame} on the same track (project copy).")
    raise error(f"Unsupported operation: {operation}")


# ---------------------------------------------------------------- mutation
def apply(project, root: ET.Element, elements: dict, operation: str, params: dict) -> None:
    if operation == "add_effect":
        item = project._instances[params["instance_id"]]
        entry = elements[item["playlist_id"]].findall("entry")[item["entry_index"]]
        service, kid, values = EFFECTS[params["effect"]]
        ids = {n.get("id") for n in root.iter() if n.get("id")}
        number = 0
        while f"copilot_filter{number}" in ids:
            number += 1
        node = ET.SubElement(entry, "filter", {"id": f"copilot_filter{number}"})
        for name, value in (("mlt_service", service), ("kdenlive_id", kid), *values.items(), ("kdenlive:collapsed", "0")):
            ET.SubElement(node, "property", {"name": name}).text = value
    elif operation == "set_track":
        track = elements[params["track_id"]]
        state = params["state"]
        if state in ("lock", "unlock"):
            _set_prop(track, "kdenlive:locked_track", "1" if state == "lock" else "0")
        else:
            ref = next(r for r in elements[params["sequence_id"]].findall("track") if r.get("producer") == params["track_id"])
            parts = _hide_set(ref.get("hide"))
            kind = "audio" if state in ("mute", "unmute") else "video"
            (parts.add if state in ("mute", "hide") else parts.discard)(kind)
            value = _hide_value(parts)
            if value is None:
                ref.attrib.pop("hide", None)
            else:
                ref.set("hide", value)
    else:
        item = project._instances[params["instance_id"]]
        playlist = elements[item["playlist_id"]]
        target = playlist.findall("entry")[item["entry_index"]]
        rows = _layout(project, playlist)
        placed = [(s, n, e) for s, n, e in rows if e is not target]
        if operation == "move_clip":
            placed.append((params["frame"], item["duration_frames"], target))
        _rebuild(playlist, placed)


# ---------------------------------------------------------------- readback
def verify(project, check, operation: str, params: dict, error) -> None:
    if operation == "add_effect":
        row = check._instances.get(params["instance_id"])
        service, kid, values = EFFECTS[params["effect"]]
        if row is None or not any(_props(f).get("mlt_service") == service and _props(f).get("kdenlive_id") == kid
                                  and all(_props(f).get(k) == v for k, v in values.items())
                                  for f in row["node"].findall("filter")):
            raise error("Effect readback verification failed.")
        before = project._instances[params["instance_id"]]
        if (row["timeline_in"], row["source_in"], row["source_out_exclusive"]) != (before["timeline_in"], before["source_in"], before["source_out_exclusive"]):
            raise error("Clip position changed while adding an effect; output not published.")
        return
    if operation == "set_track":
        track = check.elements.get(params["track_id"])
        ref = next((r for r in check.sequences[params["sequence_id"]].findall("track") if r.get("producer") == params["track_id"]), None)
        if track is None or ref is None:
            raise error("Track readback failed.")
        locked = _props(track).get("kdenlive:locked_track") == "1"
        hidden = _hide_set(ref.get("hide"))
        ok = {"lock": locked, "unlock": not locked, "mute": "audio" in hidden, "unmute": "audio" not in hidden,
              "hide": "video" in hidden, "unhide": "video" not in hidden}[params["state"]]
        if not ok:
            raise error("Track state readback verification failed.")
        return
    before = project._instances[params["instance_id"]]
    old = [(s, n, _signature(e)) for s, n, e in _layout(project, before["playlist"])]
    new = [(s, n, _signature(e)) for s, n, e in _layout(check, check.elements[before["playlist_id"]])]
    moved = next(r for r in old if r[2] == _signature(before["node"]) and r[0] == before["timeline_in"])
    expected = [r for r in old if r is not moved]
    if operation == "move_clip":
        expected.append((params["frame"], moved[1], moved[2]))
    if sorted(new, key=lambda r: r[0]) != sorted(expected, key=lambda r: r[0]):
        raise error("Clip layout readback verification failed.")
