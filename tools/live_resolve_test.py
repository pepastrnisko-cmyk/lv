"""Opt-in live acceptance test; creates a separate QA project, never edits existing ones.

Run with Blackmagic's installed ResolvePython. A parent process must impose a
deadline because native calls can block. Without --run this is read-only.
Never enable network scripting or change editor preferences to make this pass.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from editing_copilot.resolve import ResolveAdapter, ResolveError, connect_external


def main(argv=None, editor=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--allow-switch", action="store_true")
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    result = {"test": "Resolve native integration", "started_utc": datetime.now(timezone.utc).isoformat(),
              "status": "started", "steps": [], "existing_project_modified": False,
              "preferences_changed": False, "project_deleted": False}

    def record(step, details=None):
        result["steps"].append({"step": step, "details": details or {}})
        if args.result:
            args.result.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.result.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(args.result)

    original = None
    manager = None
    scratch = None
    original_name = None
    original_id = None
    try:
        resolve = editor if editor is not None else connect_external()
        result["version"] = resolve.GetVersionString()
        result["product"] = resolve.GetProductName()
        manager = resolve.GetProjectManager()
        original = manager.GetCurrentProject()
        result["active_project_exists"] = original is not None
        record("connected")
        if not args.run:
            result["status"] = "connected_read_only"
            record("read_only_probe_complete")
            return result
        if original is not None and not args.allow_switch:
            result["status"] = "skipped_existing_project"
            result["reason"] = "An existing project is open; dirty-state cannot be checked safely. No project switch was attempted."
            record("existing_project_preserved")
            return result
        if args.sample is None or not args.sample.is_file():
            raise ValueError("A generated QA media sample is required.")
        database = manager.GetCurrentDatabase()
        result["database_type"] = database.get("DbType") if isinstance(database, dict) else "unknown"
        if str(result["database_type"]).casefold() not in ("disk", "sqlite", "local"):
            result["status"] = "skipped_nonlocal_database"
            result["reason"] = "QA mutations are restricted to a confirmed local project library."
            record("database_preserved")
            return result
        original_name = original.GetName() if original is not None else None
        original_id = original.GetUniqueId() if original is not None else None
        qa_name = "Copilot_QA_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        result["qa_project_name"] = qa_name
        scratch = manager.CreateProject(qa_name)
        if scratch is None:
            raise RuntimeError("Resolve did not create the unique QA project.")
        record("scratch_project_created", {"project_id": scratch.GetUniqueId()})
        if original_id is not None and scratch.GetUniqueId() == original_id:
            raise RuntimeError("QA project identity unexpectedly matches the prior project. No edit attempted.")
        media_pool = scratch.GetMediaPool()
        imported = media_pool.ImportMedia([{"FilePath": str(args.sample.resolve())}])
        if not imported or len(imported) != 1:
            raise RuntimeError("Resolve did not import the generated sample exactly once.")
        record("sample_imported")
        timeline = media_pool.CreateTimelineFromClips("Copilot QA Timeline", [{"mediaPoolItem": imported[0]}])
        if timeline is None:
            raise RuntimeError("Resolve did not create the QA timeline.")
        if scratch.SetCurrentTimeline(timeline) is not True:
            raise RuntimeError("Resolve did not select the QA timeline.")
        record("scratch_timeline_created", {"timeline_id": timeline.GetUniqueId(),
                                            "start_frame": timeline.GetStartFrame(), "end_frame": timeline.GetEndFrame()})
        adapter = ResolveAdapter(resolve)
        snapshot = adapter.describe()
        if snapshot["identity"]["project_id"] != str(scratch.GetUniqueId()):
            raise RuntimeError("Current project does not match the isolated QA project.")
        if len(snapshot["clips"]) < 1:
            raise RuntimeError("QA timeline inspection did not return an imported clip.")
        result["inspection"] = {"clip_count": len(snapshot["clips"]), "identity": snapshot["identity"],
                                "frame_convention": snapshot["frame_convention"]}
        record("inspection_verified")
        before = snapshot["markers"]
        length = snapshot["identity"]["end_frame"] - snapshot["identity"]["start_frame"]
        if length < 2:
            raise RuntimeError("QA sample produced a timeline that is too short.")
        frame = min(10, length - 2)
        plan = adapter.plan("add_marker", {"frame": frame, "name": "Copilot live QA marker", "color": "Green"})
        record("marker_plan_created", {"plan": plan})
        transaction = adapter.apply(plan)
        record("marker_applied", {"transaction": transaction})
        after = adapter.describe()["markers"]
        if str(frame) not in after or after[str(frame)]["customData"] != transaction["marker"]["customData"]:
            raise RuntimeError("Independent live readback did not find the owned marker at its frame offset.")
        record("marker_position_and_ownership_verified", {"offset_frame": frame})
        if not adapter.apply(plan).get("idempotent"):
            raise RuntimeError("Repeated application was not idempotent.")
        record("idempotence_verified")
        undo = adapter.undo(transaction)
        if undo.get("status") != "undone" or adapter.describe()["markers"] != before:
            raise RuntimeError("Explicit undo did not restore the exact initial marker map.")
        record("explicit_undo_verified")
        current = manager.GetCurrentProject()
        if current is None or current.GetUniqueId() != scratch.GetUniqueId():
            raise RuntimeError("Current project changed before QA save. No save was attempted.")
        if manager.SaveProject() is not True:
            raise RuntimeError("QA project could not be saved.")
        record("scratch_project_saved")
        result["status"] = "passed"
        record("native_acceptance_complete")
    except Exception as exc:
        result["status"] = "unavailable" if isinstance(exc, ResolveError) and exc.code in ("not_installed", "connection_unavailable") else "failed"
        result["error"] = str(exc)
        result["code"] = getattr(exc, "code", "integration_failed")
        record("exception")
    finally:
        if scratch is not None and original is not None:
            try:
                restored = manager.LoadProject(original_name)
                result["original_project_restored"] = restored is not None and restored.GetUniqueId() == original_id
                if not result["original_project_restored"]:
                    result["status"] = "failed"
                    result["restore_error"] = "Prior project identity could not be restored."
                record("original_project_restore_checked")
            except Exception as exc:
                result["status"] = "failed"
                result["restore_error"] = str(exc)
                record("original_project_restore_failed")
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        record("finished")
    return result


if __name__ == "__main__":
    outcome = main()
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    sys.exit(0 if outcome["status"] in ("passed", "connected_read_only") else 2)
