"""Read-only Kdenlive project inspector: sequences, tracks, clips, effects, transitions.

Uses the same hardened reader as ``kdenlive.py`` (size limit, no DTD/entities,
UTF-8 only) and never writes anything. Optional ffprobe metadata is attached
per media file and degrades gracefully when ffprobe is unavailable.
"""
from __future__ import annotations

import os
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

from .kdenlive import KdenliveError, _parse, _props, _read
from .media import probe_media

_SOURCE_TAGS = ("producer", "chain")
_GENERATED = {"color", "colour", "qtext", "kdenlivetitle", "frei0r.test_pat_B", "noise", "count", "tone"}


def _int(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _filters(node: ET.Element) -> list[dict]:
    effects = []
    for f in node.findall("filter"):
        p = _props(f)
        effects.append({"id": f.get("id"), "service": p.get("mlt_service"),
                        "kdenlive_id": p.get("kdenlive_id"),
                        "name": p.get("kdenlive_id") or p.get("mlt_service") or f.get("id"),
                        "disabled": p.get("disable") == "1",
                        "internal": p.get("internal_added") is not None})
    return effects


class KdenliveInspector:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser().resolve()
        if self.path.suffix.lower() != ".kdenlive":
            raise KdenliveError("Select a saved .kdenlive project.")
        self.root = _parse(_read(self.path))
        profile = self.root.find("profile")
        self.fps = None
        self.profile = {}
        if profile is not None:
            num, den = _int(profile.get("frame_rate_num")), _int(profile.get("frame_rate_den"))
            if num > 0 and den > 0:
                self.fps = Fraction(num, den)
            self.profile = {"width": _int(profile.get("width")) or None, "height": _int(profile.get("height")) or None,
                            "fps": round(float(self.fps), 3) if self.fps else None,
                            "description": profile.get("description")}
        self.elements = {n.get("id"): n for n in self.root if n.get("id")}

    # -- sources -----------------------------------------------------------
    def _source(self, ident: str) -> dict:
        node = self.elements.get(ident)
        if node is None or node.tag not in _SOURCE_TAGS:
            return {"id": ident, "kind": node.tag if node is not None else "missing"}
        p = _props(node)
        service = p.get("mlt_service")
        resource = p.get("resource")
        local = None
        if resource and service not in _GENERATED:
            candidate = Path(resource)
            if not candidate.is_absolute():
                root_dir = self.root.get("root") or str(self.path.parent)
                candidate = Path(root_dir) / candidate
            local = str(candidate)
        return {"id": ident, "kind": node.tag, "name": p.get("kdenlive:clipname") or (Path(resource).name if resource else ident),
                "service": service, "resource": resource, "file": local, "bin_id": p.get("kdenlive:id"),
                "effects": _filters(node)}

    def media(self) -> list[dict]:
        return [self._source(i) for i, n in self.elements.items() if n.tag in _SOURCE_TAGS
                and not _props(n).get("kdenlive:playlistid")]

    # -- timeline ----------------------------------------------------------
    def _playlist_clips(self, playlist: ET.Element) -> list[dict]:
        clips, position = [], 0
        for child in playlist:
            if child.tag == "blank":
                position += max(0, _int(child.get("length")))
            elif child.tag == "entry":
                cin, cout = _int(child.get("in")), _int(child.get("out"))
                length = max(0, cout - cin + 1)
                src = child.get("producer") or ""
                info = self._source(src)
                clips.append({"producer": src, "name": info.get("name", src), "timeline_in": position,
                              "timeline_out_exclusive": position + length, "source_in": cin,
                              "source_out_exclusive": cout + 1, "effects": _filters(child)})
                position += length
        return clips

    def _track(self, ident: str, hide: str | None, depth: int) -> dict:
        node = self.elements.get(ident)
        # MLT "hide" on a sequence track: "audio" hides audio (video track), "video" hides video
        # (audio track), "both" disables the track entirely.
        track = {"id": ident, "name": ident, "type": "audio" if hide == "video" else "video",
                 "locked": False, "hide": hide, "disabled": hide == "both",
                 "clips": [], "effects": []}
        if node is None:
            track["missing"] = True
            return track
        p = _props(node)
        if node.tag == "tractor" and depth < 4:
            track.update(name=p.get("kdenlive:track_name") or ident,
                         type="audio" if p.get("kdenlive:audio_track") == "1" else track["type"],
                         locked=p.get("kdenlive:locked_track") == "1", effects=_filters(node))
            for lane_index, sub in enumerate(node.findall("track")):
                lane = self.elements.get(sub.get("producer") or "")
                if lane is not None and lane.tag == "playlist":
                    for clip in self._playlist_clips(lane):
                        clip["lane"] = lane_index
                        track["clips"].append(clip)
        elif node.tag == "playlist":
            track["clips"] = self._playlist_clips(node)
        else:
            track.update(kind="background", type="background", name=p.get("kdenlive:playlistid") or ident)
        return track

    def sequences(self) -> list[dict]:
        out = []
        for ident, node in self.elements.items():
            if node.tag != "tractor":
                continue
            p = _props(node)
            if not p.get("kdenlive:uuid"):
                continue
            tracks = [self._track(t.get("producer") or "", t.get("hide"), 1) for t in node.findall("track")]
            transitions = []
            for tr in node.findall("transition"):
                tp = _props(tr)
                transitions.append({"id": tr.get("id"), "service": tp.get("mlt_service"),
                                    "a_track": _int(tp.get("a_track"), None), "b_track": _int(tp.get("b_track"), None),
                                    "internal": tp.get("internal_added") is not None})
            out.append({"id": ident, "name": p.get("kdenlive:clipname") or ident,
                        "duration_frames": _int(p.get("kdenlive:duration")) or None,
                        "tracks": tracks, "transitions": transitions, "effects": _filters(node)})
        return out

    def inspect(self, probe: bool = False, ffprobe: str | None = None, runner=None) -> dict:
        media = self.media()
        if probe:
            seen = {}
            for item in media:
                f = item.get("file")
                if f:
                    if f not in seen:
                        seen[f] = probe_media(f, ffprobe, runner=runner) if runner else probe_media(f, ffprobe)
                    item["probe"] = seen[f]
        sequences = self.sequences()
        clip_count = sum(len(t["clips"]) for s in sequences for t in s["tracks"])
        effect_count = sum(len(c["effects"]) for s in sequences for t in s["tracks"] for c in t["clips"]) + \
            sum(len(t["effects"]) for s in sequences for t in s["tracks"])
        return {"read_only": True, "path": str(self.path), "profile": self.profile,
                "version": (_props(self.elements["main_bin"]).get("kdenlive:docproperties.version")
                            if "main_bin" in self.elements else None),
                "media": media, "sequences": sequences,
                "summary": {"sequences": len(sequences), "tracks": sum(len(s["tracks"]) for s in sequences),
                            "clips": clip_count, "effects": effect_count, "media": len(media)}}


def inspect_project(path, probe: bool = False, ffprobe: str | None = None) -> dict:
    return KdenliveInspector(path).inspect(probe=probe, ffprobe=ffprobe)
