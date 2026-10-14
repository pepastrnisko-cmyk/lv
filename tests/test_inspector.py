"""Read-only Kdenlive inspector and ffprobe media info."""
import json, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from editing_copilot.inspector import KdenliveInspector, inspect_project
from editing_copilot.kdenlive import KdenliveError
from editing_copilot import media

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "simple.kdenlive"
DEMO = HERE.parent / "resources" / "demo.kdenlive"

RICH = """<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="main_bin" version="7.30.0" root="{root}">
  <profile frame_rate_num="30000" frame_rate_den="1001" width="1920" height="1080" description="HD 29.97"/>
  <chain id="chain0" out="299">
    <property name="resource">clip.mp4</property>
    <property name="mlt_service">avformat-novalidate</property>
    <property name="kdenlive:clipname">Interview</property>
    <property name="kdenlive:id">2</property>
  </chain>
  <producer id="music" out="999">
    <property name="resource">C:/missing/song.wav</property>
    <property name="mlt_service">avformat</property>
  </producer>
  <producer id="bg" out="10"><property name="mlt_service">color</property><property name="resource">black</property>
    <property name="kdenlive:playlistid">black_track</property></producer>
  <playlist id="v_a">
    <blank length="25"/>
    <entry producer="chain0" in="0" out="49">
      <filter id="f1"><property name="mlt_service">avfilter.gblur</property><property name="kdenlive_id">gblur</property></filter>
      <filter id="f2"><property name="mlt_service">brightness</property><property name="disable">1</property></filter>
    </entry>
  </playlist>
  <playlist id="v_b"/>
  <playlist id="a_a"><entry producer="music" in="100" out="199"/></playlist>
  <playlist id="a_b"/>
  <tractor id="vt"><property name="kdenlive:track_name">V1</property><property name="kdenlive:locked_track">1</property>
    <track producer="v_a"/><track producer="v_b"/>
    <filter id="tf"><property name="mlt_service">frei0r.colgate</property></filter></tractor>
  <tractor id="at"><property name="kdenlive:track_name">A1</property><property name="kdenlive:audio_track">1</property>
    <track producer="a_a" hide="video"/><track producer="a_b" hide="video"/></tractor>
  <tractor id="{{11111111-2222-3333-4444-555555555555}}">
    <property name="kdenlive:uuid">{{11111111-2222-3333-4444-555555555555}}</property>
    <property name="kdenlive:clipname">Main</property><property name="kdenlive:duration">300</property>
    <track producer="bg"/><track producer="at" hide="video"/><track producer="vt" hide="audio"/>
    <transition id="mix"><property name="mlt_service">mix</property><property name="a_track">0</property><property name="b_track">1</property><property name="internal_added">237</property></transition>
  </tractor>
  <playlist id="main_bin"><property name="kdenlive:docproperties.version">1.1</property></playlist>
</mlt>
"""


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "rich.kdenlive"
        self.path.write_text(RICH.format(root=self.dir.as_posix()), encoding="utf-8")

    def test_fixture_tracks_and_clips(self):
        before = FIXTURE.read_bytes()
        report = inspect_project(FIXTURE)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["profile"]["fps"], 25.0)
        seq = report["sequences"][0]
        self.assertEqual(seq["name"], "Test sequence")
        video = [t for t in seq["tracks"] if t["name"] == "Video 1"][0]
        self.assertEqual([(c["timeline_in"], c["timeline_out_exclusive"]) for c in video["clips"]], [(5, 55), (65, 90)])
        self.assertEqual(video["clips"][0]["name"], "Red test card")
        self.assertEqual(seq["transitions"][0]["service"], "qtblend")
        self.assertEqual(report["summary"]["clips"], 2)
        self.assertEqual(FIXTURE.read_bytes(), before)
        json.dumps(report)

    def test_rich_project_effects_audio_locked(self):
        report = KdenliveInspector(self.path).inspect()
        seq = report["sequences"][0]
        by_name = {t["name"]: t for t in seq["tracks"]}
        v1, a1 = by_name["V1"], by_name["A1"]
        self.assertTrue(v1["locked"]); self.assertEqual(v1["type"], "video")
        self.assertEqual(a1["type"], "audio"); self.assertFalse(a1["locked"])
        clip = v1["clips"][0]
        self.assertEqual((clip["timeline_in"], clip["timeline_out_exclusive"]), (25, 75))
        self.assertEqual([e["name"] for e in clip["effects"]], ["gblur", "brightness"])
        self.assertEqual([e["disabled"] for e in clip["effects"]], [False, True])
        self.assertEqual(v1["effects"][0]["service"], "frei0r.colgate")
        self.assertEqual(a1["clips"][0]["source_in"], 100)
        self.assertEqual(report["profile"]["fps"], 29.97)
        self.assertEqual(report["summary"]["effects"], 3)
        files = {m["id"]: m["file"] for m in report["media"]}
        self.assertEqual(Path(files["chain0"]), self.dir / "clip.mp4")
        self.assertNotIn("bg", files)

    def test_probe_degrades_without_ffprobe(self):
        with patch.object(media, "find_ffprobe", return_value=None):
            report = KdenliveInspector(self.path).inspect(probe=True)
        probes = [m["probe"] for m in report["media"] if "probe" in m]
        self.assertEqual(len(probes), 2)
        self.assertTrue(all(p["available"] is False and p["ok"] is False for p in probes))

    def test_unsafe_or_wrong_files_rejected(self):
        bad = self.dir / "x.kdenlive"; bad.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><mlt/>', encoding="utf-8")
        with self.assertRaises(KdenliveError):
            inspect_project(bad)
        with self.assertRaises(KdenliveError):
            inspect_project(self.dir / "x.mp4")

    def test_demo_project_inspects(self):
        report = inspect_project(DEMO)
        self.assertGreaterEqual(report["summary"]["sequences"], 1)
        json.dumps(report)


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "a.mp4"; self.file.write_bytes(b"\0" * 16)

    def test_missing_ffprobe(self):
        with patch.object(media, "find_ffprobe", return_value=None):
            r = media.probe_media(self.file)
        self.assertEqual((r["available"], r["ok"]), (False, False)); self.assertIn("ffprobe", r["error"])

    def _run(self, **kw):
        def runner(cmd, **_):
            self.assertNotIn("shell", _)
            self.assertEqual(cmd[-1], str(self.file)); self.assertEqual(cmd[-2], "--")
            return subprocess.CompletedProcess(cmd, kw.get("rc", 0), kw.get("out", b""), kw.get("err", b""))
        with patch.object(media, "find_ffprobe", return_value="ffprobe"):
            return media.probe_media(self.file, runner=runner)

    def test_parses_streams(self):
        out = json.dumps({"format": {"format_name": "mov,mp4", "duration": "12.5", "size": "1000", "bit_rate": "640"},
                          "streams": [{"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001", "pix_fmt": "yuv420p"},
                                      {"index": 1, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}]}).encode()
        r = self._run(out=out)
        self.assertTrue(r["ok"]); self.assertEqual(r["duration_seconds"], 12.5)
        self.assertEqual(r["streams"][0]["fps"], 29.97); self.assertEqual(r["streams"][1]["sample_rate"], 48000)

    def test_failure_modes_never_raise(self):
        self.assertIn("broken", self._run(rc=1, err=b"broken")["error"])
        self.assertIn("invalid JSON", self._run(out=b"{nope")["error"])
        def slow(cmd, **_): raise subprocess.TimeoutExpired(cmd, 1)
        with patch.object(media, "find_ffprobe", return_value="ffprobe"):
            self.assertIn("timed out", media.probe_media(self.file, runner=slow)["error"])
            self.assertEqual(media.probe_media(Path(self.tmp.name) / "nope.mp4")["error"], "File not found.")

    def test_real_ffprobe_if_installed(self):
        if media.find_ffprobe() is None:
            self.skipTest("ffprobe not installed")
        r = media.probe_media(self.file)
        self.assertTrue(r["available"]); self.assertFalse(r["ok"])  # 16 zero bytes is not media


if __name__ == "__main__":
    unittest.main()
