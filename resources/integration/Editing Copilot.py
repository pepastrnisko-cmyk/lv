"""Install in Resolve's user Utility script folder.

Launch: Workspace > Scripts > Utility > Editing Copilot.
Uses Resolve's internal scripting context; no network listener, credentials,
external-scripting preference changes, or extra Python packages are required.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone


def _package_path():
    here = Path(__file__).resolve().parent
    local_base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    candidates = (here, here.parent.parent / "src", local_base / "EditingCopilot/integration")
    for candidate in candidates:
        if (candidate / "editing_copilot" / "resolve.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Editing Copilot package is missing. Reinstall the Utility script and its integration package.")


def _history_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    return base / "EditingCopilot" / "resolve-menu-history.json"


def _read_history(path):
    if not path.exists():
        return []
    if path.stat().st_size > 4 * 1024 * 1024:
        raise RuntimeError("Marker history is too large. Preserve it before resetting the history file.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != 1 or not isinstance(payload.get("transactions"), list):
        raise RuntimeError("Marker history is damaged. Preserve it before resetting the history file.")
    entries = payload["transactions"]
    if any(not isinstance(entry, dict) for entry in entries):
        raise RuntimeError("Marker history contains invalid entries. No edit was made.")
    return entries


def _prune(entries, keep=500):
    """Trim only finished records; never drop pending or applied ownership records."""
    if len(entries) <= keep:
        return entries
    live = [e for e in entries if e.get("status") in ("pending", "applied")]
    done = [e for e in entries if e.get("status") not in ("pending", "applied")]
    return (done[-max(0, keep - len(live)):] + live) if len(live) < keep else live


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(entry, **changes):
    """Return entry with updated fields and a modification time (schema 1 stays readable)."""
    entry.update(changes)
    entry["updated_utc"] = _now()
    return entry


def _write_history(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="resolve-history-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"schema": 1, "transactions": _prune(entries)}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(context):
    _package_path()
    from editing_copilot.resolve import ResolveAdapter, ResolveError, is_pre_mutation

    editor = context.get("resolve")
    if editor is None:
        raise RuntimeError("Launch this script from Resolve's Workspace > Scripts menu.")
    adapter = ResolveAdapter(editor)
    fusion = context.get("fusion") or editor.Fusion()
    bmd = context.get("bmd")
    ui = getattr(fusion, "UIManager", None) if fusion is not None else None
    if ui is None or bmd is None or not callable(getattr(bmd, "UIDispatcher", None)):
        print("Editing Copilot: this Resolve edition does not expose UIManager. No project changes were made.")
        try:
            print(json.dumps(adapter.describe(), ensure_ascii=False, indent=2))
        except Exception as exc:
            print("Inspection:", str(exc))
        print("Use the portable Editing Copilot companion for inspection and supported operations.")
        return
    dispatcher = bmd.UIDispatcher(ui)
    window_id = "org.editingcopilot.resolve.Markers.v1"
    existing = ui.FindWindow(window_id)
    if existing:
        existing.Show()
        existing.Raise()
        return
    window = dispatcher.AddWindow(
        {"ID": window_id, "WindowTitle": "Editing Copilot — Resolve", "Geometry": [120, 120, 760, 650]},
        ui.VGroup({"Spacing": 8}, [
            ui.Label({"Text": "Inspect your timeline and add verified, reversible markers.", "Weight": 0}),
            ui.Label({"Text": "Frame is an integer offset from timeline start; frame 0 is the first frame.", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "Frame", "Weight": 0.15}),
                ui.LineEdit({"ID": "Frame", "Text": "0", "Weight": 0.85})]),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "Name", "Weight": 0.15}),
                ui.LineEdit({"ID": "Name", "Text": "Copilot marker", "Weight": 0.85})]),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "Color", "Weight": 0.15}),
                ui.LineEdit({"ID": "Color", "Text": "Green", "Weight": 0.35}),
                ui.Label({"Text": "Duration", "Weight": 0.15}),
                ui.LineEdit({"ID": "Duration", "Text": "1", "Weight": 0.35})]),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "Note", "Weight": 0.15}),
                ui.LineEdit({"ID": "Note", "Text": "", "Weight": 0.85})]),
            ui.HGroup({"Weight": 0}, [
                ui.Button({"ID": "Inspect", "Text": "Inspect timeline"}),
                ui.Button({"ID": "Preview", "Text": "Preview marker"}),
                ui.Button({"ID": "Apply", "Text": "Apply preview", "Enabled": False}),
                ui.Button({"ID": "Undo", "Text": "Undo my last marker"})]),
            ui.TextEdit({"ID": "Output", "ReadOnly": True, "PlainText": "Inspection does not change your project."}),
            ui.Label({"Text": "Existing markers are preserved. Modified or moved markers are never deleted automatically.", "Weight": 0}),
            ui.Button({"ID": "Close", "Text": "Close", "Weight": 0})]))
    items = window.GetItems()
    state = {"plan": None, "history": [], "history_ok": True}
    history_file = _history_path()
    try:
        state["history"] = _read_history(history_file)
    except Exception as exc:
        state["history_ok"] = False
        items["Output"].PlainText = str(exc)

    def output(message):
        items["Output"].PlainText = str(message)

    def fields():
        frame_text = str(items["Frame"].Text).strip()
        if not frame_text.isdecimal():
            raise ValueError("Frame must be a nonnegative integer offset, for example 120.")
        duration_text = str(items["Duration"].Text).strip()
        if not (duration_text.isascii() and duration_text.isdecimal()) or int(duration_text) < 1:
            raise ValueError("Duration must be a whole number of frames, at least 1.")
        if not (frame_text.isascii()):
            raise ValueError("Frame must use plain digits 0-9.")
        return {"frame": int(frame_text), "name": str(items["Name"].Text), "note": str(items["Note"].Text),
                "color": str(items["Color"].Text).strip(), "duration": int(duration_text)}

    def inspect(event=None):
        state["plan"] = None
        items["Apply"].Enabled = False
        try:
            snapshot = adapter.describe()
            identity = snapshot["identity"]
            header = ("Project: " + identity["project_name"] + "\nTimeline: " + identity["timeline_name"] +
                      "\nResolve: " + snapshot["version"] + " (" + snapshot["product"] + ")" +
                      "\nFrames: " + str(identity["end_frame"] - identity["start_frame"]) +
                      "\nTimeline items: " + str(len(snapshot["clips"])) + "\n\n")
            output(header + json.dumps(snapshot, ensure_ascii=False, indent=2))
        except Exception as exc:
            output(str(exc))

    def preview(event=None):
        state["plan"] = None
        items["Apply"].Enabled = False
        try:
            if not state["history_ok"]:
                raise RuntimeError("History could not be read. Repair it before adding markers.")
            state["plan"] = adapter.plan("add_marker", fields())
            items["Apply"].Enabled = True
            output("READY TO APPLY\n" + json.dumps(state["plan"], ensure_ascii=False, indent=2))
        except Exception as exc:
            output(str(exc))

    def apply(event=None):
        plan = state["plan"]
        items["Apply"].Enabled = False
        state["plan"] = None
        try:
            if plan is None:
                raise RuntimeError("Preview a marker first.")
            current = fields()
            expected = dict(plan["marker"])
            expected.pop("customData", None)
            if current.pop("frame") != plan["frame"] or current != expected:
                raise RuntimeError("Marker fields changed after preview. Create a new preview.")
            record = _stamp(adapter._transaction(plan), status="pending", created_utc=_now())
            state["history"].append(record)
            # Ownership must be durable BEFORE the host is touched. If this fails, nothing was changed.
            _write_history(history_file, state["history"])
            try:
                transaction = adapter.apply(plan)
            except Exception as exc:
                if is_pre_mutation(exc):
                    _stamp(record, status="cancelled", error=getattr(exc, "code", "error"))
                    note = "No change was made to your project."
                else:
                    note = ("The outcome is UNKNOWN. Inspect the timeline before another operation. "
                            "The pending history record keeps ownership so Undo can still find the marker.")
                try:
                    _write_history(history_file, state["history"])
                except Exception as write_exc:
                    note += "\nHistory could not be updated: " + str(write_exc)
                output(str(exc) + "\n" + note)
                return
            transaction["created_utc"] = record["created_utc"]
            state["history"][-1] = _stamp(transaction)
            try:
                _write_history(history_file, state["history"])
            except Exception as write_exc:
                output("VERIFIED, but history could not be saved: " + str(write_exc) +
                       "\nThe marker exists. Do not retry; inspect the timeline.")
                return
            extra = ("\n" + transaction["message"]) if transaction.get("message") else ""
            output("VERIFIED\n" + transaction["summary"] + extra + "\nUse Undo my last marker to reverse this operation.")
        except Exception as exc:
            output(str(exc) + "\nNo change was made to your project.")

    def undo(event=None):
        items["Apply"].Enabled = False
        state["plan"] = None
        try:
            if not state["history_ok"]:
                raise RuntimeError("History could not be read. Undo is disabled.")
            snapshot = adapter.describe()
            identity = snapshot["identity"]
            match = next((entry for entry in reversed(state["history"])
                          if entry.get("status") in ("applied", "pending") and
                          entry.get("identity", {}).get("project_id") == identity["project_id"] and
                          entry.get("identity", {}).get("timeline_id") == identity["timeline_id"]), None)
            if match is None:
                raise RuntimeError("No assistant marker is recorded for this timeline.")
            result = adapter.undo(match)
            _stamp(match, status="undone")
            try:
                _write_history(history_file, state["history"])
            except Exception as write_exc:
                output("VERIFIED UNDO, but history could not be saved: " + str(write_exc))
                return
            output("VERIFIED UNDO\n" + json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            output(str(exc))

    def close(event=None):
        dispatcher.ExitLoop()

    window.On[window_id].Close = close
    window.On["Close"].Clicked = close
    window.On["Inspect"].Clicked = inspect
    window.On["Preview"].Clicked = preview
    window.On["Apply"].Clicked = apply
    window.On["Undo"].Clicked = undo
    window.Show()
    if state["history_ok"]:
        inspect()
    try:
        dispatcher.RunLoop()
    finally:
        window.Hide()


if __name__ == "__main__":
    try:
        main(globals())
    except Exception as exc:
        print("Editing Copilot:", str(exc))
