"""Bounded, verified DaVinci Resolve integration; standard library only.

The API contract is the installed Resolve scripting developer documentation.
Only project inspection and assistant-owned timeline markers are enabled.
Frames passed to add_marker are integer offsets from the timeline start, not
absolute timecode frames. No project is opened, created, saved, or deleted here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid


OWNER_PREFIX = "editing-copilot/v1/"
COLORS = frozenset(("Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple",
                    "Fuchsia", "Rose", "Lavender", "Sky", "Mint", "Lemon",
                    "Sand", "Cocoa", "Cream"))
MAX_CLIPS = 20000


class ResolveError(RuntimeError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def connect_external():
    """Connect through Blackmagic's installed module. Call in an isolated worker.

    Native scripting calls may block. The desktop application's worker deadline
    must enforce responsiveness; this function does not start or configure Resolve.
    """
    try:
        import DaVinciResolveScript as module
    except ImportError:
        candidates = []
        supplied = os.environ.get("RESOLVE_SCRIPT_API")
        if supplied:
            candidates.append(Path(supplied) / "Modules" / "DaVinciResolveScript.py")
        if sys.platform == "win32":
            candidates.append(Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) /
                              "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules/DaVinciResolveScript.py")
        elif sys.platform == "darwin":
            candidates.append(Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules/DaVinciResolveScript.py"))
        else:
            candidates.append(Path("/opt/resolve/Developer/Scripting/Modules/DaVinciResolveScript.py"))
        module_file = next((p for p in candidates if p.is_file()), None)
        if module_file is None:
            raise ResolveError("not_installed", "Resolve scripting module was not found. Install Resolve or use its Scripts menu.")
        try:
            spec = importlib.util.spec_from_file_location("DaVinciResolveScript", str(module_file))
            module = importlib.util.module_from_spec(spec)
            # Blackmagic's wrapper replaces this entry with the native module.
            # Register before executing, matching normal import semantics.
            sys.modules["DaVinciResolveScript"] = module
            spec.loader.exec_module(module)
            module = sys.modules["DaVinciResolveScript"]
        except Exception as exc:
            if sys.modules.get("DaVinciResolveScript") is module:
                sys.modules.pop("DaVinciResolveScript", None)
            raise ResolveError("connection_unavailable", "The installed Resolve scripting module could not load. Use Workspace > Scripts > Utility > Editing Copilot.") from exc
    try:
        resolve = module.scriptapp("Resolve")
    except Exception as exc:
        raise ResolveError("connection_unavailable", "Resolve did not accept an external scripting connection. Open Resolve and use the in-editor script.") from exc
    if resolve is None:
        raise ResolveError("connection_unavailable", "No Resolve scripting connection. Open a project, or use Workspace > Scripts > Utility > Editing Copilot. Studio external access requires Local scripting in preferences.")
    return resolve


def _cancelled(cancel):
    if cancel is None:
        return False
    if callable(cancel):
        return bool(cancel())
    return bool(cancel.is_set())


def _check_cancel(cancel):
    if _cancelled(cancel):
        raise ResolveError("cancelled", "Operation cancelled before changing the project.")


def _integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResolveError("invalid_argument", field + " must be an integer number of frames.")
    return value


def _text(value, field, maximum, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ResolveError("invalid_argument", field + " must be text of at most " + str(maximum) + " characters without NUL.")
    if not allow_empty and not value.strip():
        raise ResolveError("invalid_argument", field + " cannot be empty.")
    return value


def _json_value(value):
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _markers(timeline):
    value = timeline.GetMarkers()
    if not isinstance(value, dict):
        raise ResolveError("readback_failed", "Resolve did not return a marker map. No changes were made.")
    result = {}
    for key, marker in value.items():
        if isinstance(key, bool):
            raise ResolveError("readback_failed", "Resolve returned an invalid marker position.")
        try:
            numeric = float(key)
        except (TypeError, ValueError) as exc:
            raise ResolveError("readback_failed", "Resolve returned an invalid marker position.") from exc
        if not numeric.is_integer() or not isinstance(marker, dict):
            raise ResolveError("readback_failed", "Resolve returned an invalid marker record.")
        frame = int(numeric)
        if frame in result:
            raise ResolveError("readback_failed", "Resolve returned duplicate marker positions.")
        result[frame] = _json_value(marker)
    return result


def _digest(markers):
    return hashlib.sha256(json.dumps(markers, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _marker_matches(observed, expected):
    if not isinstance(observed, dict):
        return False
    return all(observed.get(key) == expected.get(key) for key in
               ("color", "name", "note", "duration", "customData"))


def _owned(value):
    if not isinstance(value, str) or not value.startswith(OWNER_PREFIX):
        return False
    try:
        suffix = value[len(OWNER_PREFIX):]
        return str(uuid.UUID(suffix)) == suffix
    except (ValueError, AttributeError):
        return False


class ResolveAdapter:
    """Inject a Resolve object/callable for testing, or connect to the local editor."""
    def __init__(self, connect=None):
        self.resolve = (connect() if callable(connect) else connect) if connect is not None else connect_external()
        if self.resolve is None:
            raise ResolveError("connection_unavailable", "Resolve is not connected.")

    def _context(self):
        manager = self.resolve.GetProjectManager()
        project = manager.GetCurrentProject() if manager is not None else None
        if project is None:
            raise ResolveError("no_project", "Open a Resolve project first.")
        timeline = project.GetCurrentTimeline()
        if timeline is None:
            raise ResolveError("no_timeline", "Open a timeline in the current project first.")
        get_project_id = getattr(project, "GetUniqueId", None)
        get_timeline_id = getattr(timeline, "GetUniqueId", None)
        project_id = get_project_id() if callable(get_project_id) else None
        timeline_id = get_timeline_id() if callable(get_timeline_id) else None
        identity = {"project_id": str(project_id) if project_id else None,
                    "project_name": str(project.GetName()),
                    "timeline_id": str(timeline_id) if timeline_id else None,
                    "timeline_name": str(timeline.GetName()),
                    "start_frame": int(timeline.GetStartFrame()),
                    "end_frame": int(timeline.GetEndFrame())}
        return manager, project, timeline, identity

    @staticmethod
    def _assert_identity(identity, expected):
        if not identity["project_id"] or not identity["timeline_id"]:
            raise ResolveError("identity_unavailable", "Stable project and timeline identifiers are required for editing.")
        if identity != expected:
            raise ResolveError("stale_plan", "The project or timeline changed. Inspect it and create a new preview.")

    @staticmethod
    def _assert_idle(project):
        check = getattr(project, "IsRenderingInProgress", None)
        if not callable(check):
            raise ResolveError("state_unavailable", "Resolve render state cannot be checked. Editing is disabled.")
        state = check()
        if state is not False:
            raise ResolveError("editor_busy", "Resolve is rendering or its render state is unavailable. Wait before editing.")

    def describe(self):
        """Return a JSON-safe read-only snapshot of the active project/timeline."""
        _, project, timeline, identity = self._context()
        get_settings = getattr(timeline, "GetSettings", None)
        if not callable(get_settings):
            get_settings = getattr(timeline, "GetSetting", None)
        settings = get_settings() if callable(get_settings) else {}
        clips = []
        for track_type in ("video", "audio", "subtitle"):
            count = timeline.GetTrackCount(track_type)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > 1000:
                raise ResolveError("readback_failed", "Resolve returned an invalid track count.")
            for index in range(1, count + 1):
                items = timeline.GetItemListInTrack(track_type, index) or []
                for item in items:
                    if len(clips) >= MAX_CLIPS:
                        raise ResolveError("project_too_large", "This inspection is limited to 20,000 timeline items.")
                    get_id = getattr(item, "GetUniqueId", None)
                    get_properties = getattr(item, "GetProperties", None)
                    if not callable(get_properties):
                        get_properties = getattr(item, "GetProperty", None)
                    clips.append({"id": str(get_id()) if callable(get_id) else None,
                                  "name": str(item.GetName()), "track_type": track_type,
                                  "track": index, "start_frame": item.GetStart(),
                                  "end_frame": item.GetEnd(), "duration_frames": item.GetDuration(),
                                  "properties": _json_value(get_properties() or {}) if callable(get_properties) else {}})
        get_version = getattr(self.resolve, "GetVersionString", None)
        get_product = getattr(self.resolve, "GetProductName", None)
        product = str(get_product()) if callable(get_product) else "DaVinci Resolve"
        result = {"editor": "resolve", "connected": True,
                  "version": str(get_version()) if callable(get_version) else "unknown",
                  "product": product, "edition": "Studio" if "studio" in product.lower() else "unconfirmed",
                  "scope": "active project and timeline", "identity": identity,
                  "settings": _json_value(settings or {}), "clips": clips,
                  "markers": {str(k): v for k, v in _markers(timeline).items()},
                  "capabilities": ["inspect", "add_marker", "undo_owned_marker"],
                  "frame_convention": "Marker frame is a zero-based offset from timeline start.",
                  "unsupported": ["color_matching", "grading", "ripple_edit", "export", "arbitrary_ui_control"]}
        return result

    def plan(self, operation, args=None):
        args = args or {}
        if operation == "inspect":
            return {"editor": "resolve", "operation": "inspect"}
        if operation != "add_marker":
            raise ResolveError("unsupported_operation", "This Resolve build supports inspection and verified timeline markers only.")
        if not isinstance(args, dict):
            raise ResolveError("invalid_argument", "Marker arguments must be a dictionary.")
        unknown = set(args) - {"frame", "name", "note", "color", "duration"}
        if unknown:
            raise ResolveError("invalid_argument", "Unknown marker arguments: " + ", ".join(sorted(unknown)))
        frame = _integer(args.get("frame"), "frame")
        duration = _integer(args.get("duration", 1), "duration")
        name = _text(args.get("name", "Copilot marker"), "name", 256)
        note = _text(args.get("note", ""), "note", 4096, True)
        color = args.get("color", "Green")
        if color not in COLORS:
            raise ResolveError("invalid_argument", "Choose a documented Resolve marker color.")
        _, project, timeline, identity = self._context()
        self._assert_identity(identity, identity)
        self._assert_idle(project)
        length = identity["end_frame"] - identity["start_frame"]
        if frame < 0 or duration <= 0 or frame + duration > length:
            raise ResolveError("out_of_range", "Marker frame and duration must fit inside the timeline (zero-based offsets).")
        markers = _markers(timeline)
        if frame in markers:
            raise ResolveError("marker_conflict", "A marker already exists at that frame. Existing markers are never overwritten.")
        marker = {"name": name, "note": note, "color": color, "duration": duration,
                  "customData": OWNER_PREFIX + str(uuid.uuid4())}
        return {"editor": "resolve", "operation": "add_marker", "identity": identity,
                "frame": frame, "marker": marker, "before_markers_digest": _digest(markers),
                "summary": "Add '" + name + "' at offset frame " + str(frame) + " in " + identity["timeline_name"],
                "reversible": True, "requires_user_apply": True}

    def _validate_plan(self, plan):
        if not isinstance(plan, dict) or plan.get("editor") != "resolve" or plan.get("operation") != "add_marker":
            raise ResolveError("invalid_plan", "Invalid Resolve marker plan.")
        marker = plan.get("marker")
        if not isinstance(marker, dict) or not _owned(marker.get("customData")):
            raise ResolveError("invalid_plan", "The marker plan has no valid assistant ownership record.")
        frame = _integer(plan.get("frame"), "frame")
        duration = _integer(marker.get("duration"), "duration")
        _text(marker.get("name"), "name", 256)
        _text(marker.get("note"), "note", 4096, True)
        if marker.get("color") not in COLORS:
            raise ResolveError("invalid_plan", "Invalid marker color.")
        _, project, timeline, identity = self._context()
        self._assert_identity(identity, plan.get("identity"))
        self._assert_idle(project)
        if frame < 0 or duration < 1 or frame + duration > identity["end_frame"] - identity["start_frame"]:
            raise ResolveError("out_of_range", "Marker does not fit inside the active timeline.")
        return project, timeline, identity

    @staticmethod
    def _transaction(plan):
        return {"editor": "resolve", "operation": "add_marker", "status": "applied",
                "id": plan["marker"]["customData"][len(OWNER_PREFIX):],
                "identity": dict(plan["identity"]), "frame": plan["frame"],
                "marker": dict(plan["marker"]), "reversible": True,
                "summary": plan.get("summary", "Added assistant-owned timeline marker")}

    def apply(self, plan, cancel=None):
        _check_cancel(cancel)
        if isinstance(plan, dict) and plan.get("operation") == "inspect":
            return self.describe()
        _, timeline, _ = self._validate_plan(plan)
        frame, marker = plan["frame"], plan["marker"]
        before = _markers(timeline)
        transaction = self._transaction(plan)
        if _marker_matches(before.get(frame), marker):
            transaction["idempotent"] = True
            return transaction
        if any(m.get("customData") == marker["customData"] for m in before.values()):
            raise ResolveError("marker_conflict", "This marker ownership record already appears elsewhere. Inspect before retrying.")
        if frame in before or _digest(before) != plan.get("before_markers_digest"):
            raise ResolveError("stale_plan", "Timeline markers changed after preview. Create a new preview.")
        _check_cancel(cancel)
        returned = timeline.AddMarker(frame, marker["color"], marker["name"], marker["note"],
                                      marker["duration"], marker["customData"])
        try:
            after = _markers(timeline)
        except Exception as exc:
            raise ResolveError("verification_failed", "The marker call completed but readback failed. Do not retry blindly; inspect the timeline.", {"transaction": transaction}) from exc
        if not _marker_matches(after.get(frame), marker):
            raise ResolveError("verification_failed", "Resolve did not verify the exact intended marker. Inspect the timeline before continuing.", {"transaction": transaction, "api_return": bool(returned)})
        if _cancelled(cancel):
            transaction["stopped_after_apply"] = True
            transaction["message"] = "Stopped after the marker was applied and verified. Use explicit Undo to remove it."
        return transaction

    def undo(self, transaction, cancel=None):
        _check_cancel(cancel)
        _, timeline, _ = self._validate_plan(transaction)
        frame, marker = transaction["frame"], transaction["marker"]
        markers = _markers(timeline)
        if frame not in markers:
            if any(m.get("customData") == marker["customData"] for m in markers.values()):
                raise ResolveError("undo_conflict", "The assistant marker moved. It will not be deleted automatically.")
            return {"editor": "resolve", "operation": "undo_owned_marker", "status": "undone",
                    "id": transaction.get("id"), "idempotent": True}
        if not _marker_matches(markers[frame], marker):
            raise ResolveError("undo_conflict", "The marker changed after the assistant created it. Undo would erase later work.")
        duplicates = sum(m.get("customData") == marker["customData"] for m in markers.values())
        if duplicates != 1:
            raise ResolveError("undo_conflict", "Marker ownership is ambiguous. No marker was removed.")
        _check_cancel(cancel)
        returned = timeline.DeleteMarkerAtFrame(frame)
        after = _markers(timeline)
        if frame in after or any(m.get("customData") == marker["customData"] for m in after.values()):
            raise ResolveError("verification_failed", "Resolve did not verify marker removal. Inspect the timeline.", {"api_return": bool(returned)})
        return {"editor": "resolve", "operation": "undo_owned_marker", "status": "undone",
                "id": transaction.get("id"), "idempotent": False}
