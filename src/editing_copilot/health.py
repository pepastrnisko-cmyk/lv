"""Read-only media health check for a Kdenlive project (uses ffprobe when available)."""
from __future__ import annotations

from pathlib import Path

from .inspector import KdenliveInspector


def media_health(path, ffprobe: str | None = None, runner=None) -> dict:
    """Report missing files, unreadable media and frame-rate mismatches. Never modifies anything."""
    inspector = KdenliveInspector(path)
    report = inspector.inspect(probe=True, ffprobe=ffprobe, runner=runner)
    project_fps = report["profile"].get("fps")
    issues, checked, ffprobe_available = [], 0, None
    for item in report["media"]:
        file = item.get("file")
        if not file:
            continue  # generated clips (colour, titles) have no file
        checked += 1
        name = item.get("name") or item["id"]
        if not Path(file).is_file():
            issues.append({"severity": "error", "media": name, "file": file, "issue": "missing_file",
                           "message": f"Media file not found: {file}"})
            continue
        probe = item.get("probe") or {}
        if ffprobe_available is None:
            ffprobe_available = bool(probe.get("available"))
        if not probe.get("available"):
            continue
        if not probe.get("ok"):
            issues.append({"severity": "error", "media": name, "file": file, "issue": "unreadable",
                           "message": f"ffprobe could not read the file: {probe.get('error')}"})
            continue
        video = [s for s in probe.get("streams", []) if s.get("type") == "video"]
        fps = video[0].get("fps") if video else None
        if fps and project_fps and abs(fps - project_fps) > 0.01 and len(video) == 1 and probe.get("duration_seconds"):
            issues.append({"severity": "warning", "media": name, "file": file, "issue": "fps_mismatch",
                           "message": f"Clip is {fps} fps but the project is {project_fps} fps."})
    if checked and ffprobe_available is False:
        issues.append({"severity": "info", "issue": "ffprobe_unavailable",
                       "message": "ffprobe not found: only file existence was checked. Install FFmpeg or set EC_FFPROBE."})
    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    summary = (f"Media health: {checked} file(s) checked, {errors} error(s), {warnings} warning(s)."
               if checked else "Media health: no file-based media in this project.")
    return {"read_only": True, "path": report["path"], "project_fps": project_fps, "files_checked": checked,
            "ffprobe_available": ffprobe_available, "issues": issues, "ok": errors == 0, "summary": summary,
            "media": report["media"]}


def project_details(path) -> dict:
    """Compact read-only summary for the 'inspect project details' command."""
    report = KdenliveInspector(path).inspect(probe=False)
    seqs = []
    for s in report["sequences"]:
        seqs.append({"id": s["id"], "name": s["name"], "transitions": len(s["transitions"]),
                     "tracks": [{"id": t["id"], "name": t["name"], "type": t["type"], "locked": t["locked"],
                                 "hide": t.get("hide"), "clips": len(t["clips"]),
                                 "effects": [e["name"] for e in t["effects"]],
                                 "clip_effects": sorted({e["name"] for c in t["clips"] for e in c["effects"] if e.get("name")})}
                                for t in s["tracks"] if t.get("type") != "background"]})
    return {"read_only": True, "profile": report["profile"], "summary": report["summary"], "sequences": seqs}
