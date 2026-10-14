"""'inspect project details' and 'check media' commands (read-only)."""
import json, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from editing_copilot import media
from editing_copilot.commands import parse_command
from editing_copilot.health import media_health, project_details
from editing_copilot.nlu import interpret
from editing_copilot.runtime import Controller

FIXTURE = Path(__file__).parent / "fixtures" / "simple.kdenlive"

PROJECT = """<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="main_bin" version="7.30.0" root="{root}">
  <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
  <producer id="a" out="99"><property name="resource">present.mp4</property><property name="mlt_service">avformat</property></producer>
  <producer id="b" out="99"><property name="resource">gone.mp4</property><property name="mlt_service">avformat</property></producer>
  <producer id="c" out="99"><property name="resource">#ff0000</property><property name="mlt_service">color</property></producer>
  <playlist id="main_bin"><property name="kdenlive:docproperties.version">1.1</property></playlist>
</mlt>
"""

PROBE = {"format": {"format_name": "mov", "duration": "4.0"},
         "streams": [{"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"}]}


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "present.mp4").write_bytes(b"x")
        self.path = self.dir / "p.kdenlive"
        self.path.write_text(PROJECT.format(root=self.dir.as_posix()), encoding="utf-8")

    def test_missing_file_and_no_ffprobe(self):
        before = self.path.read_bytes()
        with patch.object(media, "find_ffprobe", return_value=None):
            r = media_health(self.path)
        kinds = sorted(i["issue"] for i in r["issues"])
        self.assertEqual(kinds, ["ffprobe_unavailable", "missing_file"])
        self.assertFalse(r["ok"]); self.assertEqual(r["files_checked"], 2)
        self.assertEqual(self.path.read_bytes(), before)
        json.dumps(r)

    def test_fps_mismatch_with_ffprobe(self):
        def runner(cmd, **_):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(PROBE).encode(), b"")
        with patch.object(media, "find_ffprobe", return_value="ffprobe"):
            r = media_health(self.path, runner=runner)
        issues = {i["issue"]: i for i in r["issues"]}
        self.assertIn("fps_mismatch", issues); self.assertIn("missing_file", issues)
        self.assertNotIn("ffprobe_unavailable", issues)
        self.assertIn("30.0 fps", issues["fps_mismatch"]["message"])

    def test_project_details_fixture(self):
        d = project_details(FIXTURE)
        self.assertEqual(d["summary"]["clips"], 2)
        self.assertEqual(d["sequences"][0]["tracks"][0]["name"], "Video 1")


class CommandTests(unittest.TestCase):
    def test_grammar(self):
        for text in ("inspect project details", "Project details"):
            self.assertEqual(parse_command(text).operation, "inspect_details")
        for text in ("check media", "media health", "Check media health"):
            self.assertEqual(parse_command(text).operation, "media_health")
        self.assertEqual(parse_command("inspect project").operation, "inspect")  # unchanged

    def test_voice(self):
        self.assertEqual(interpret("copilot check media").kind, "command")
        intent = interpret("inspect project details")
        self.assertEqual((intent.kind, intent.value), ("command", "inspect project details"))
        self.assertEqual(interpret("inspect").kind, "control")  # unchanged

    def test_controller(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "s.kdenlive"; src.write_bytes(FIXTURE.read_bytes())
        c = Controller(Path(tmp.name) / "data"); self.addCleanup(c.close)
        c.select("kdenlive", src)
        r = c.plan("inspect project details")
        self.assertEqual(r["operation"], "inspect_details"); self.assertIn("2 clip(s)", r["summary"])
        self.assertIsNone(c.preview)
        h = c.plan("check media")
        self.assertEqual(h["operation"], "media_health"); self.assertTrue(h["health"]["ok"])
        self.assertIsNone(c.preview)
        self.assertEqual(src.read_bytes(), FIXTURE.read_bytes())
        c.select("resolve")
        with self.assertRaises(ValueError):
            c.plan("check media")


if __name__ == "__main__":
    unittest.main()
