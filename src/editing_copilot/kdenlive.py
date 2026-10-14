"""Conservative, offline Kdenlive project-copy adapter (document format 1.1).

There is deliberately no live GUI automation here. Edits are previewed as plans,
then written to a *new* file. Only saved state is observed. Times are frames;
source/timeline intervals in this API are half-open, unlike MLT's inclusive out.

Format references: KDE/kdenlive/dev-docs/fileformat.md and
src/bin/model/markerlistmodel.cpp (KDE upstream, consulted 2026-10-13).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from fractions import Fraction
from typing import Any
import xml.etree.ElementTree as ET

MAX_PROJECT_BYTES = 32 * 1024 * 1024
MAX_ELEMENTS = 200_000
MAX_DEPTH = 128
SUPPORTED_OPERATIONS = ("add_guide", "trim", "split")


class KdenliveError(ValueError):
    """Invalid, changed, ambiguous, or unsupported project/operation."""


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > 2_147_483_647:
        raise KdenliveError(f"{label} must be an integer from {minimum} to 2147483647.")
    return value


def _props(node: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for prop in node.findall("property"):
        name = prop.get("name")
        if not name or name in result:
            raise KdenliveError("Missing or duplicate XML property name.")
        result[name] = prop.text or ""
    return result


def _setprop(node: ET.Element, name: str, value: str) -> None:
    for child in node.findall("property"):
        if child.get("name") == name:
            child.text = value
            return
    ET.SubElement(node, "property", {"name": name}).text = value


def _read(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_PROJECT_BYTES + 1)
    except OSError as exc:
        raise KdenliveError(f"Cannot read project: {exc}") from exc
    if len(data) > MAX_PROJECT_BYTES:
        raise KdenliveError("Project exceeds the 32 MiB safety limit.")
    return data


def _parse(data: bytes) -> ET.Element:
    # Restrict encodings: this ensures the declaration scan cannot be bypassed
    # with UTF-16/32 null bytes. Standard Kdenlive output is UTF-8.
    if b"\x00" in data or re.search(br"<!\s*(DOCTYPE|ENTITY)", data, re.I):
        raise KdenliveError("DTD/entities and non-UTF-8 XML are not supported.")
    try:
        text = data.decode("utf-8-sig")
        declaration = re.match(r"\s*<\?xml\s+([^?]+)\?>", text)
        if declaration:
            encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)", declaration[1], re.I)
            if encoding and encoding[1].lower() not in ("utf-8", "utf8"):
                raise KdenliveError("Only UTF-8 Kdenlive XML is supported.")
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(text, parser=parser)
    except (UnicodeError, ET.ParseError) as exc:
        raise KdenliveError(f"Invalid project XML: {exc}") from exc
    if root.tag != "mlt":
        raise KdenliveError("Expected an MLT project root.")
    stack = [(root, 0)]
    count = 0
    ids = set()
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_ELEMENTS or depth > MAX_DEPTH:
            raise KdenliveError("XML complexity exceeds the safety limit.")
        identifier = node.get("id")
        if identifier:
            if identifier in ids:
                raise KdenliveError(f"Duplicate XML element ID: {identifier}")
            ids.add(identifier)
        if node.tag == "property":
            if list(node):
                raise KdenliveError("Nested XML in property is unsupported.")
        else:
            _props(node)
        stack.extend((child, depth + 1) for child in node)
    return root


def _json_array(value: str, label: str) -> list:
    try:
        result = json.loads(value or "[]")
    except (ValueError, RecursionError) as exc:
        raise KdenliveError(f"Malformed {label} JSON.") from exc
    if not isinstance(result, list):
        raise KdenliveError(f"{label} must be a JSON array.")
    return result


class KdenliveProject:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser().resolve()
        if self.path.suffix.lower() != ".kdenlive":
            raise KdenliveError("Select a saved .kdenlive project.")
        self.data = _read(self.path)
        self.source_hash = hashlib.sha256(self.data).hexdigest()
        self.root = _parse(self.data)
        profiles = self.root.findall("profile")
        if len(profiles) != 1:
            raise KdenliveError("Exactly one project profile is required.")
        try:
            numerator = int(profiles[0].get("frame_rate_num", "0"))
            denominator = int(profiles[0].get("frame_rate_den", "0"))
            if numerator < 1 or denominator < 1:
                raise ValueError()
            self.fps = Fraction(numerator, denominator)
            if self.fps > 1000:
                raise ValueError()
        except (ValueError, ZeroDivisionError) as exc:
            raise KdenliveError("Invalid project frame rate.") from exc
        self.elements: dict[str, ET.Element] = {}
        for node in self.root:
            identifier = node.get("id")
            if identifier:
                if identifier in self.elements:
                    raise KdenliveError(f"Duplicate element ID: {identifier}")
                self.elements[identifier] = node
        self.bin = self.elements.get("main_bin")
        if self.bin is None or self.bin.tag != "playlist":
            raise KdenliveError("Project bin main_bin is missing.")
        self.bin_properties = _props(self.bin)
        self.version = self.bin_properties.get("kdenlive:docproperties.version", "unknown")
        self.sequences = {i: n for i, n in self.elements.items()
                          if n.tag == "tractor" and _props(n).get("kdenlive:uuid")}
        self._instances: dict[str, dict] = {}
        self._sequence_description = self._inspect_sequences()

    def _frames(self, value: str | None) -> int:
        if value is None:
            raise KdenliveError("An explicit frame boundary is required.")
        if re.fullmatch(r"\d+", value):
            return _integer(int(value), "MLT frame value")
        clock = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)\.(\d+)", value)
        if clock:
            hours, minutes, seconds, fraction = clock.groups()
            time = (int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                    + Fraction(int(fraction), 10 ** len(fraction)))
            frame_value = time * self.fps
            # MLT saves milliseconds, which quantize fractional-rate frames.
            rounded = (frame_value.numerator * 2 + frame_value.denominator) // (2 * frame_value.denominator)
            if abs(frame_value - rounded) > self.fps / 2000 + Fraction(1, 1_000_000):
                raise KdenliveError(f"Time is not aligned to a frame: {value}")
            return _integer(rounded, "MLT clock value")
        raise KdenliveError(f"Unsupported MLT time representation: {value}")

    def _inspect_sequences(self) -> list[dict]:
        results = []
        for seq_id, seq in self.sequences.items():
            tracks = []
            for track_number, reference in enumerate(seq.findall("track")):
                track_id = reference.get("producer", "")
                track = self.elements.get(track_id)
                if track is None:
                    raise KdenliveError(f"Missing track reference: {track_id}")
                if track.tag != "tractor":
                    continue  # implicit black background
                track_props = _props(track)
                playlists = []
                for lane in track.findall("track"):
                    playlist_id = lane.get("producer", "")
                    playlist = self.elements.get(playlist_id)
                    if playlist is None or playlist.tag != "playlist":
                        raise KdenliveError("Unsupported timeline track layout: expected playlists.")
                    cursor = 0
                    entries = []
                    entry_number = 0
                    for item in playlist:
                        if item.tag == "blank":
                            cursor += self._frames(item.get("length"))
                        elif item.tag == "entry":
                            producer_id = item.get("producer", "")
                            producer = self.elements.get(producer_id)
                            if producer is None:
                                raise KdenliveError(f"Missing producer: {producer_id}")
                            start = self._frames(item.get("in"))
                            end = self._frames(item.get("out")) + 1
                            if end <= start:
                                raise KdenliveError("Clip has an invalid inclusive MLT range.")
                            instance_id = f"{seq_id}|{playlist_id}|{entry_number}"
                            properties = _props(producer)
                            row = {"instance_id": instance_id, "producer_id": producer_id,
                                   "asset_id": _props(item).get("kdenlive:id") or properties.get("kdenlive:id"),
                                   "name": properties.get("kdenlive:clipname", producer_id),
                                   "source_in": start, "source_out_exclusive": end,
                                   "timeline_in": cursor, "timeline_out_exclusive": cursor + end - start,
                                   "duration_frames": end - start, "track_id": track_id,
                                   "playlist_id": playlist_id, "sequence_id": seq_id,
                                   "entry_index": entry_number}
                            entries.append(row)
                            self._instances[instance_id] = {**row, "node": item, "producer": producer,
                                                            "playlist": playlist, "track": track, "sequence": seq}
                            entry_number += 1
                            cursor += end - start
                    playlists.append({"id": playlist_id, "duration_frames": cursor, "instances": entries})
                tracks.append({"id": track_id, "index": track_number,
                               "name": track_props.get("kdenlive:track_name", track_id),
                               "audio": track_props.get("kdenlive:audio_track") == "1",
                               "locked": track_props.get("kdenlive:locked_track") == "1",
                               "playlists": playlists})
            guides = _json_array(_props(seq).get("kdenlive:sequenceproperties.guides", "[]"), "guides")
            results.append({"id": seq_id, "name": _props(seq).get("kdenlive:clipname", seq_id),
                            "tracks": tracks, "guides": guides})
        return results

    def describe(self) -> dict:
        assets = []
        for entry in self.bin.findall("entry"):
            producer_id = entry.get("producer", "")
            producer = self.elements.get(producer_id)
            if producer is None:
                raise KdenliveError(f"Missing bin producer: {producer_id}")
            props = _props(producer)
            assets.append({"producer_id": producer_id, "asset_id": props.get("kdenlive:id"),
                           "name": props.get("kdenlive:clipname", producer_id),
                           "resource": props.get("resource"), "service": props.get("mlt_service"),
                           "sequence": producer_id in self.sequences})
        profile = self.root.find("profile")
        return {"editor": "kdenlive", "path": str(self.path), "source_sha256": self.source_hash,
                "document_version": self.version,
                "frame_rate": {"numerator": self.fps.numerator, "denominator": self.fps.denominator},
                "fps": float(self.fps), "width": profile.get("width"), "height": profile.get("height"),
                "assets": assets, "sequences": copy.deepcopy(self._sequence_description),
                "supported_operations": list(SUPPORTED_OPERATIONS) if self.version == "1.1" and self.sequences else [],
                "limitations": ["Saved project only; unsaved editor changes are not visible.",
                                "Trim/split require simple ungrouped effect-free clips.",
                                "Output is a new project copy; reopen it in Kdenlive."]}

    def _simple_instance(self, identifier: str) -> dict:
        if not isinstance(identifier, str):
            raise KdenliveError("Timeline instance ID must be a string.")
        item = self._instances.get(identifier)
        if item is None:
            raise KdenliveError("Unknown timeline instance; inspect the project again.")
        if set(item["node"].attrib) != {"producer", "in", "out"}:
            raise KdenliveError("Unrecognized timeline-entry attributes prevent safe trim/split.")
        track_references = [ref for seq in self.sequences.values() for ref in seq.findall("track")
                            if ref.get("producer") == item["track_id"]]
        playlist_references = [ref for node in self.elements.values() if node.tag == "tractor"
                               for ref in node.findall("track") if ref.get("producer") == item["playlist_id"]]
        if len(track_references) != 1 or len(playlist_references) != 1:
            raise KdenliveError("Shared timeline tracks/playlists are unsupported for trim/split.")
        if any(entry.get("producer") == item["sequence_id"] for node in self.elements.values()
               if node.tag == "playlist" and node is not self.bin for entry in node.findall("entry")):
            raise KdenliveError("Editing a sequence used inside another sequence is unsupported.")
        seq_props = _props(item["sequence"])
        groups = _json_array(seq_props.get("kdenlive:sequenceproperties.groups", "[]"), "groups")
        global_groups = _json_array(self.bin_properties.get("kdenlive:docproperties.groups", "[]"), "groups")
        if groups or global_groups:
            raise KdenliveError("Trim/split of grouped or linked clips is unsupported.")
        for node in (item["track"], item["playlist"]):
            props = _props(node)
            if any(props.get(key) == "1" for key in ("kdenlive:locked_track", "kdenlive:locked")):
                raise KdenliveError("Target track is locked.")
        if item["producer"].tag not in ("producer", "chain"):
            raise KdenliveError("Nested sequences are unsupported for trim/split.")
        service = _props(item["producer"]).get("mlt_service", "")
        if service not in ("avformat", "avformat-novalidate", "color", "qimage", "pixbuf"):
            raise KdenliveError("Retimed or unknown producer service is unsupported for trim/split.")
        if any(list(node.findall("filter")) for node in (item["producer"], item["node"], item["playlist"], item["track"])):
            raise KdenliveError("Trim/split of clips or tracks with effects is unsupported.")
        for node in (item["track"], item["playlist"]):
            if node.findall("transition"):
                raise KdenliveError("Same-track mixes are unsupported for trim/split.")
        if any(_props(t).get("internal_added") != "237" for t in item["sequence"].findall("transition")):
            raise KdenliveError("User compositions are unsupported for trim/split.")
        for lane in item["track"].findall("track"):
            if lane.get("producer") != item["playlist_id"]:
                other = self.elements[lane.get("producer")]
                if other.findall("entry"):
                    raise KdenliveError("Active second playlist/mix lane is unsupported.")
        if any(child.tag != "property" for child in item["node"]):
            raise KdenliveError("Unknown timeline-entry children are unsupported for trim/split.")
        # Metadata potentially encoding instance IDs or temporal effect information.
        known_entry_props = {"kdenlive:id", "kdenlive:maxduration"}
        if set(_props(item["node"])) - known_entry_props:
            raise KdenliveError("Unrecognized timeline-entry metadata prevents safe trim/split.")
        return item

    def plan(self, operation: str, args: dict) -> dict:
        if self.version != "1.1" or not self.sequences:
            raise KdenliveError("Editing supports generation-5 Kdenlive document version 1.1 only.")
        if not isinstance(args, dict):
            raise KdenliveError("Operation arguments must be an object.")
        params = copy.deepcopy(args)
        summary = ""
        if operation == "add_guide":
            if set(params) - {"sequence_id", "frame", "comment", "category"}:
                raise KdenliveError("Unknown guide argument.")
            seq_id = params.get("sequence_id")
            if seq_id is None and len(self.sequences) == 1:
                seq_id = next(iter(self.sequences))
            if not isinstance(seq_id, str) or seq_id not in self.sequences:
                raise KdenliveError("Select an exact timeline sequence.")
            frame = _integer(params.get("frame"), "Guide frame")
            category = _integer(params.get("category", 0), "Guide category")
            comment = params.get("comment")
            if not isinstance(comment, str) or not comment.strip() or len(comment) > 4096:
                raise KdenliveError("Guide comment must contain 1 to 4096 characters.")
            if any(ord(ch) < 32 and ch not in "\n\t\r" for ch in comment):
                raise KdenliveError("Guide comment contains XML-invalid control characters.")
            # Reject lone surrogates and other XML-invalid scalar values.
            if any(0xD800 <= ord(ch) <= 0xDFFF or ord(ch) in (0xFFFE, 0xFFFF) for ch in comment):
                raise KdenliveError("Guide comment contains XML-invalid characters.")
            categories = _json_array(self.bin_properties.get("kdenlive:docproperties.guidesCategories", "[]"), "guide categories")
            if not categories or not all(isinstance(c, dict) and type(c.get("index")) is int for c in categories):
                raise KdenliveError("Explicit valid project guide categories are required.")
            if category not in {c["index"] for c in categories}:
                raise KdenliveError("Guide category does not exist in this project.")
            guides = _json_array(_props(self.sequences[seq_id]).get("kdenlive:sequenceproperties.guides", "[]"), "guides")
            if not all(isinstance(g, dict) and type(g.get("pos")) is int and 0 <= g["pos"] <= 2_147_483_647
                       and isinstance(g.get("comment", ""), str) and type(g.get("type", 0)) is int
                       and type(g.get("duration", 0)) is int and g.get("duration", 0) >= 0 for g in guides):
                raise KdenliveError("Existing guide schema is unsupported.")
            if len({g["pos"] for g in guides}) != len(guides):
                raise KdenliveError("Duplicate existing guide positions are unsupported.")
            if any(g["pos"] == frame for g in guides):
                raise KdenliveError("A guide already exists at that frame.")
            params = {"sequence_id": seq_id, "frame": frame, "comment": comment, "category": category}
            summary = f"Add timeline guide at frame {frame}: {comment}"
        elif operation in ("trim", "split"):
            expected = {"instance_id", "source_in", "source_out_exclusive"} if operation == "trim" else {"instance_id", "frame"}
            if set(params) != expected:
                raise KdenliveError(f"{operation} requires exactly these arguments: {sorted(expected)}")
            item = self._simple_instance(params.get("instance_id"))
            if operation == "trim":
                start = _integer(params["source_in"], "Source in")
                end = _integer(params["source_out_exclusive"], "Exclusive source out", 1)
                if not item["source_in"] <= start < end <= item["source_out_exclusive"]:
                    raise KdenliveError("Trim must retain a nonempty range inside the current clip.")
                if start == item["source_in"] and end == item["source_out_exclusive"]:
                    raise KdenliveError("Trim would make no change.")
                summary = f"Trim {item['name']} to source frames [{start}, {end}); preserve surrounding timeline positions with gaps."
            else:
                frame = _integer(params["frame"], "Split timeline frame")
                if not item["timeline_in"] < frame < item["timeline_out_exclusive"]:
                    raise KdenliveError("Split frame must lie strictly inside the target clip.")
                summary = f"Split {item['name']} at timeline frame {frame}; preserve duration."
        else:
            raise KdenliveError(f"Unsupported operation: {operation}. Supported: {', '.join(SUPPORTED_OPERATIONS)}")
        return {"schema_version": 1, "editor": "kdenlive", "operation": operation, "args": params,
                "source_path": str(self.path), "source_sha256": self.source_hash, "summary": summary,
                "verification": "saved-project structural readback; editor reopen/render must be checked separately"}

    def apply(self, plan: dict, output: str | os.PathLike[str], cancel: threading.Event | None = None) -> dict:
        def check_cancel() -> None:
            if cancel is not None and cancel.is_set():
                raise KdenliveError("Operation cancelled before publication.")
        check_cancel()
        if not isinstance(plan, dict) or plan.get("source_sha256") != self.source_hash or plan.get("source_path") != str(self.path):
            raise KdenliveError("Plan belongs to another project snapshot.")
        # Recompute the plan: never trust mutable serialized operations or summaries.
        approved = self.plan(plan.get("operation"), plan.get("args"))
        if approved != plan:
            raise KdenliveError("Plan was modified; generate a fresh preview.")
        if hashlib.sha256(_read(self.path)).hexdigest() != self.source_hash:
            raise KdenliveError("Source project changed after inspection; reload and replan.")
        destination = Path(output).expanduser().resolve()
        if destination.suffix.lower() != ".kdenlive":
            raise KdenliveError("Output must be a new .kdenlive file.")
        if destination == self.path or destination.exists():
            raise KdenliveError("Output already exists or refers to the source; overwriting is prohibited.")
        if not destination.parent.is_dir():
            raise KdenliveError("Output folder does not exist.")
        root = copy.deepcopy(self.root)
        elements = {n.get("id"): n for n in root if n.get("id")}
        params = approved["args"]
        operation = approved["operation"]
        if operation == "add_guide":
            seq = elements[params["sequence_id"]]
            guides = _json_array(_props(seq).get("kdenlive:sequenceproperties.guides", "[]"), "guides")
            guides.append({"pos": params["frame"], "comment": params["comment"], "type": params["category"], "duration": 0})
            guides.sort(key=lambda g: g["pos"])
            _setprop(seq, "kdenlive:sequenceproperties.guides", json.dumps(guides, ensure_ascii=False, indent=2))
        else:
            item = self._instances[params["instance_id"]]
            playlist = elements[item["playlist_id"]]
            entry = playlist.findall("entry")[item["entry_index"]]
            index = list(playlist).index(entry)
            if operation == "split":
                source_cut = item["source_in"] + params["frame"] - item["timeline_in"]
                second = copy.deepcopy(entry)
                entry.set("out", str(source_cut - 1))
                second.set("in", str(source_cut))
                playlist.insert(index + 1, second)
            else:
                head = params["source_in"] - item["source_in"]
                tail = item["source_out_exclusive"] - params["source_out_exclusive"]
                entry.set("in", str(params["source_in"]))
                entry.set("out", str(params["source_out_exclusive"] - 1))
                if head:
                    playlist.insert(index, ET.Element("blank", {"length": str(head)}))
                    index += 1
                if tail:
                    playlist.insert(index + 1, ET.Element("blank", {"length": str(tail)}))
        # Keep relative assets rooted at the *original* project directory. The
        # main file may be copied elsewhere. Do not rewrite resource strings.
        old_root = root.get("root", "")
        if not old_root:
            root.set("root", str(self.path.parent))
        elif not Path(old_root).is_absolute():
            root.set("root", str((self.path.parent / old_root).resolve()))
        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        _parse(data)
        check_cancel()
        temp_name = None
        published = False
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".editing-copilot-", suffix=".kdenlive", dir=destination.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            check_cancel()
            # Structural readback from disk before publishing.
            check = KdenliveProject(temp_name)
            if operation == "add_guide":
                actual = _json_array(_props(check.sequences[params["sequence_id"]]).get("kdenlive:sequenceproperties.guides", "[]"), "guides")
                if not any(g.get("pos") == params["frame"] and g.get("comment") == params["comment"] and g.get("type") == params["category"] for g in actual):
                    raise KdenliveError("Guide readback verification failed.")
            else:
                before = self._instances[params["instance_id"]]
                actual_entries = [r for r in check._instances.values() if r["playlist_id"] == before["playlist_id"] and r["sequence_id"] == before["sequence_id"]]
                old_duration = sum(self._frames(n.get("length")) if n.tag == "blank" else self._frames(n.get("out")) - self._frames(n.get("in")) + 1 for n in before["playlist"] if n.tag in ("entry", "blank"))
                new_playlist = check.elements[before["playlist_id"]]
                new_duration = sum(check._frames(n.get("length")) if n.tag == "blank" else check._frames(n.get("out")) - check._frames(n.get("in")) + 1 for n in new_playlist if n.tag in ("entry", "blank"))
                if old_duration != new_duration:
                    raise KdenliveError("Timeline duration readback failed.")
                if operation == "trim" and not any(r["source_in"] == params["source_in"] and r["source_out_exclusive"] == params["source_out_exclusive"] and r["timeline_in"] == before["timeline_in"] + params["source_in"] - before["source_in"] for r in actual_entries):
                    raise KdenliveError("Trim range readback failed.")
                if operation == "split" and not any(r["timeline_in"] == params["frame"] for r in actual_entries):
                    raise KdenliveError("Split readback failed.")
            if hashlib.sha256(_read(self.path)).hexdigest() != self.source_hash:
                raise KdenliveError("Source changed during operation; output was not published.")
            check_cancel()
            # Hard-link publication is atomic and refuses an existing name on
            # both Windows and POSIX. Never fall back to overwrite-prone replace.
            try:
                os.link(temp_name, destination)
            except FileExistsError as exc:
                raise KdenliveError("Output appeared during operation; not overwritten.") from exc
            published = True
            return {"status": "completed", "editor": "kdenlive", "operation": operation,
                    "output": str(destination), "source_sha256": self.source_hash,
                    "output_sha256": hashlib.sha256(data).hexdigest(), "source_unchanged": True,
                    "verification": "structural_readback_passed", "editor_reopen_verified": False,
                    "summary": approved["summary"]}
        except OSError as exc:
            raise KdenliveError(f"Cannot publish project copy: {exc}") from exc
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except OSError:
                    # Publication already succeeded; keep a recoverable temp
                    # rather than delete the user-facing file.
                    if not published:
                        pass
