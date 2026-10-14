"""Project-copy edits: allowlisted effects, track state, move and delete clip."""
import shutil, tempfile, unittest
from pathlib import Path

from editing_copilot.kdenlive import KdenliveError, KdenliveProject
from editing_copilot.kdenlive_ops import EFFECTS, canonical_effect

FIXTURE = Path(__file__).parent / "fixtures" / "simple.kdenlive"

AUDIO = FIXTURE.read_text(encoding="utf-8").replace(
    '<playlist id="empty_lane" />',
    '<playlist id="empty_lane" />\n  <playlist id="a_lane" />\n  <playlist id="a_lane2" />\n'
    '  <tractor id="audio_track" in="0" out="99"><property name="kdenlive:track_name">Audio 1</property>'
    '<property name="kdenlive:audio_track">1</property><property name="kdenlive:locked_track">0</property>'
    '<track producer="a_lane" hide="video" /><track producer="a_lane2" hide="video" /></tractor>').replace(
    '<track producer="video_track" />', '<track producer="audio_track" />\n    <track producer="video_track" />')


class OpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "src.kdenlive"; shutil.copyfile(FIXTURE, self.src)
        self.n = 0

    def run_op(self, op, args, src=None):
        project = KdenliveProject(src or self.src)
        before = (src or self.src).read_bytes()
        plan = project.plan(op, args)
        self.n += 1
        out = self.dir / f"out{self.n}.kdenlive"
        result = project.apply(plan, out)
        self.assertEqual(result["verification"], "structural_readback_passed")
        self.assertEqual((src or self.src).read_bytes(), before, "source must never change")
        return plan, KdenliveProject(out)

    def clips(self, project):
        return [r for r in project.describe()["sequences"][0]["tracks"][0]["playlists"][0]["instances"]]

    def first(self):
        return self.clips(KdenliveProject(self.src))[0]

    def test_effect_allowlist_and_aliases(self):
        self.assertEqual(canonical_effect("Black and White"), "greyscale")
        self.assertEqual(canonical_effect("blur"), "gaussian blur")
        self.assertIsNone(canonical_effect("lua script"))
        with self.assertRaises(KdenliveError):
            KdenliveProject(self.src).plan("add_effect", {"instance_id": self.first()["instance_id"], "effect": "lua script"})

    def test_add_effect(self):
        clip = self.first()
        plan, out = self.run_op("add_effect", {"instance_id": clip["instance_id"], "effect": "Sepia"})
        self.assertEqual(plan["args"]["effect"], "sepia")
        node = out._instances[clip["instance_id"]]["node"]
        services = [p.text for f in node.findall("filter") for p in f.findall("property") if p.get("name") == "mlt_service"]
        self.assertEqual(services, ["sepia"])
        self.assertEqual(self.clips(out)[0]["timeline_in"], clip["timeline_in"])
        # duplicate effect on the copy is refused
        with self.assertRaises(KdenliveError):
            KdenliveProject(out.path).plan("add_effect", {"instance_id": clip["instance_id"], "effect": "sepia"})
        # trim/split stay refused on clips with effects (existing safety rule)
        with self.assertRaises(KdenliveError):
            KdenliveProject(out.path).plan("split", {"instance_id": clip["instance_id"], "frame": clip["timeline_in"] + 5})

    def test_every_allowlisted_effect_applies(self):
        clip = self.first()
        for name in EFFECTS:
            with self.subTest(effect=name):
                self.run_op("add_effect", {"instance_id": clip["instance_id"], "effect": name})

    def test_lock_unlock_and_locked_blocks_edits(self):
        _, locked = self.run_op("set_track", {"track_id": "video_track", "state": "lock"})
        self.assertTrue(locked.describe()["sequences"][0]["tracks"][0]["locked"])
        clip = self.clips(locked)[0]
        for op, args in (("add_effect", {"effect": "sepia"}), ("delete_clip", {}), ("move_clip", {"frame": 0})):
            with self.subTest(op=op), self.assertRaises(KdenliveError):
                KdenliveProject(locked.path).plan(op, {"instance_id": clip["instance_id"], **args})
        with self.assertRaises(KdenliveError):
            KdenliveProject(locked.path).plan("set_track", {"track_id": "video_track", "state": "lock"})
        _, unlocked = self.run_op("set_track", {"track_id": "video_track", "state": "unlock"}, src=locked.path)
        self.assertFalse(unlocked.describe()["sequences"][0]["tracks"][0]["locked"])

    def test_hide_video_and_mute_audio(self):
        _, hidden = self.run_op("set_track", {"track_id": "video_track", "state": "hide"})
        ref = [r for r in hidden.sequences["{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}"].findall("track") if r.get("producer") == "video_track"][0]
        self.assertEqual(ref.get("hide"), "video")
        _, shown = self.run_op("set_track", {"track_id": "video_track", "state": "unhide"}, src=hidden.path)
        ref = [r for r in shown.sequences["{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}"].findall("track") if r.get("producer") == "video_track"][0]
        self.assertIsNone(ref.get("hide"))
        with self.assertRaises(KdenliveError):
            KdenliveProject(self.src).plan("set_track", {"track_id": "video_track", "state": "mute"})
        audio = self.dir / "audio.kdenlive"; audio.write_text(AUDIO, encoding="utf-8")
        _, muted = self.run_op("set_track", {"track_id": "audio_track", "state": "mute"}, src=audio)
        ref = [r for r in muted.sequences["{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}"].findall("track") if r.get("producer") == "audio_track"][0]
        self.assertEqual(ref.get("hide"), "audio")
        with self.assertRaises(KdenliveError):
            KdenliveProject(audio).plan("set_track", {"track_id": "audio_track", "state": "hide"})
        with self.assertRaises(KdenliveError):
            KdenliveProject(self.src).plan("set_track", {"track_id": "nope", "state": "lock"})

    def test_move_clip(self):
        a, b = self.clips(KdenliveProject(self.src))
        _, out = self.run_op("move_clip", {"instance_id": a["instance_id"], "frame": 0})
        rows = self.clips(out)
        self.assertEqual([(r["timeline_in"], r["timeline_out_exclusive"]) for r in rows], [(0, 50), (65, 90)])
        self.assertEqual(rows[0]["source_in"], a["source_in"])
        project = KdenliveProject(self.src)
        for frame in (40, 60, 80, a["timeline_in"]):  # overlap b / overlap / past end / no-op
            with self.subTest(frame=frame), self.assertRaises(KdenliveError):
                project.plan("move_clip", {"instance_id": a["instance_id"], "frame": frame})
        with self.assertRaises(KdenliveError):
            project.plan("move_clip", {"instance_id": a["instance_id"], "frame": -1})

    def test_move_clip_into_gap_next_to_other(self):
        a, b = self.clips(KdenliveProject(self.src))
        _, out = self.run_op("move_clip", {"instance_id": b["instance_id"], "frame": 55})
        rows = self.clips(out)
        self.assertEqual([(r["timeline_in"], r["source_in"]) for r in rows], [(5, 10), (55, 0)])

    def test_delete_clip_leaves_gap_and_needs_confirmation(self):
        a, b = self.clips(KdenliveProject(self.src))
        plan, out = self.run_op("delete_clip", {"instance_id": a["instance_id"]})
        self.assertTrue(plan["requires_confirmation"])
        rows = self.clips(out)
        self.assertEqual([(r["timeline_in"], r["timeline_out_exclusive"]) for r in rows], [(65, 90)])
        plan2, out2 = self.run_op("delete_clip", {"instance_id": rows[0]["instance_id"]}, src=out.path)
        self.assertEqual(self.clips(out2), [])

    def test_tampered_plan_rejected(self):
        project = KdenliveProject(self.src)
        plan = project.plan("delete_clip", {"instance_id": self.first()["instance_id"]})
        plan["args"]["instance_id"] = self.clips(project)[1]["instance_id"]
        with self.assertRaises(KdenliveError):
            project.apply(plan, self.dir / "x.kdenlive")
        self.assertFalse((self.dir / "x.kdenlive").exists())

    def test_existing_operations_unchanged(self):
        plan = KdenliveProject(self.src).plan("add_guide", {"frame": 3, "comment": "x"})
        self.assertNotIn("requires_confirmation", plan)
        self.assertEqual(list(plan), ["schema_version", "editor", "operation", "args", "source_path", "source_sha256", "summary", "verification"])


if __name__ == "__main__":
    unittest.main()
