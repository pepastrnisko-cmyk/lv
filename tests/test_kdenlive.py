"""Offline safety and frame-accurate project-copy tests; no live project edits."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from editing_copilot.kdenlive import KdenliveError, KdenliveProject, _parse

FIXTURE = Path(__file__).parent / "fixtures" / "simple.kdenlive"
SEQUENCE = "{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}"


class KdenliveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "source.kdenlive"
        self.source.write_bytes(FIXTURE.read_bytes())
        self.project = KdenliveProject(self.source)
        self.instance = self.project.describe()["sequences"][0]["tracks"][0]["playlists"][0]["instances"][0]["instance_id"]

    def mutate(self, callback):
        root = ET.fromstring(self.source.read_bytes())
        callback(root)
        self.source.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
        return KdenliveProject(self.source)

    def guide(self, project=None):
        return (project or self.project).plan("add_guide", {"frame": 12, "comment": "Review skin tones"})

    def instances(self, project):
        return project.describe()["sequences"][0]["tracks"][0]["playlists"][0]["instances"]

    def test_describe_distinguishes_assets_and_instances(self):
        description = self.project.describe()
        self.assertEqual(description["frame_rate"], {"numerator": 25, "denominator": 1})
        clips = self.instances(self.project)
        self.assertEqual(len(clips), 2)
        self.assertNotEqual(clips[0]["instance_id"], clips[1]["instance_id"])
        self.assertEqual(clips[0]["asset_id"], clips[1]["asset_id"])
        self.assertEqual(clips[0]["duration_frames"], 50)
        self.assertEqual((clips[0]["timeline_in"], clips[0]["timeline_out_exclusive"]), (5, 55))
        self.assertEqual(clips[1]["timeline_in"], 65)
        json.dumps(description)

    def test_guide_copy_source_unchanged_unknown_data_preserved(self):
        before = self.source.read_bytes()
        output = self.folder / "guided.kdenlive"
        result = self.project.apply(self.guide(), output)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(result["source_unchanged"])
        self.assertFalse(result["editor_reopen_verified"])
        after = KdenliveProject(output)
        self.assertEqual(after.describe()["sequences"][0]["guides"], [{"pos": 12, "comment": "Review skin tones", "type": 0, "duration": 0}])
        self.assertIn(b"preserve this", output.read_bytes())
        self.assertIn(b"Repeated asset use", output.read_bytes())
        self.assertEqual(after.root.get("root"), str(self.folder))
        self.assertEqual(result["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    def test_trim_preserves_surrounding_positions_and_duration(self):
        plan = self.project.plan("trim", {"instance_id": self.instance, "source_in": 20, "source_out_exclusive": 50})
        output = self.folder / "trim.kdenlive"
        self.project.apply(plan, output)
        clips = self.instances(KdenliveProject(output))
        self.assertEqual((clips[0]["timeline_in"], clips[0]["timeline_out_exclusive"]), (15, 45))
        self.assertEqual((clips[0]["source_in"], clips[0]["source_out_exclusive"]), (20, 50))
        self.assertEqual(clips[1]["timeline_in"], 65)
        playlist = ET.parse(output).find("playlist[@id='video_lane']")
        self.assertEqual(sum(int(x.get("length")) if x.tag == "blank" else int(x.get("out")) - int(x.get("in")) + 1 for x in playlist if x.tag in ("blank", "entry")), 100)

    def test_split_inclusive_out_is_exact(self):
        output = self.folder / "split.kdenlive"
        self.project.apply(self.project.plan("split", {"instance_id": self.instance, "frame": 30}), output)
        clips = self.instances(KdenliveProject(output))
        self.assertEqual(len(clips), 3)
        self.assertEqual((clips[0]["source_in"], clips[0]["source_out_exclusive"]), (10, 35))
        self.assertEqual((clips[1]["source_in"], clips[1]["source_out_exclusive"]), (35, 60))
        self.assertEqual(clips[1]["timeline_in"], 30)
        self.assertEqual(clips[2]["timeline_in"], 65)

    def test_only_exact_supported_document_version_is_editable(self):
        project = self.mutate(lambda r: setattr(r.find("playlist[@id='main_bin']/property[@name='kdenlive:docproperties.version']"), "text", "1.2"))
        self.assertEqual(project.describe()["supported_operations"], [])
        with self.assertRaises(KdenliveError):
            self.guide(project)

    def test_unknown_operation_and_arguments_rejected(self):
        for operation, args in [("match_color", {}), ("add_guide", {"frame": 1, "comment": "x", "arbitrary": True}), ("trim", {"instance_id": self.instance}), ("split", {"instance_id": "missing", "frame": 30}), ("split", {"instance_id": [], "frame": 30}), ("add_guide", {"sequence_id": [], "frame": 2, "comment": "x"})]:
            with self.subTest(operation=operation):
                with self.assertRaises(KdenliveError):
                    self.project.plan(operation, args)

    def test_invalid_guide_values(self):
        for update in ({"frame": True}, {"frame": -1}, {"frame": 1.5}, {"category": 2}, {"comment": ""}, {"comment": "a\x01"}, {"comment": "a\ud800"}, {"comment": "x" * 4097}):
            with self.subTest(update=repr(update)):
                args = {"frame": 12, "comment": "x", **update}
                with self.assertRaises(KdenliveError):
                    self.project.plan("add_guide", args)

    def test_guide_conflict_does_not_replace(self):
        output = self.folder / "guided.kdenlive"
        self.project.apply(self.guide(), output)
        with self.assertRaises(KdenliveError):
            self.guide(KdenliveProject(output))

    def test_invalid_trim_and_split_boundaries(self):
        for start, end in [(9, 60), (10, 61), (20, 20), (50, 20), (10, 60)]:
            with self.subTest(start=start, end=end):
                with self.assertRaises(KdenliveError):
                    self.project.plan("trim", {"instance_id": self.instance, "source_in": start, "source_out_exclusive": end})
        for frame in (5, 55, 0, True, 30.5):
            with self.subTest(frame=frame):
                with self.assertRaises(KdenliveError):
                    self.project.plan("split", {"instance_id": self.instance, "frame": frame})

    def test_grouped_clips_rejected(self):
        project = self.mutate(lambda r: setattr(r.find(f"tractor[@id='{SEQUENCE}']/property[@name='kdenlive:sequenceproperties.groups']"), "text", '[{"type":"AVSplit"}]'))
        with self.assertRaisesRegex(KdenliveError, "grouped"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_locked_track_rejected(self):
        project = self.mutate(lambda r: setattr(r.find("tractor[@id='video_track']/property[@name='kdenlive:locked_track']"), "text", "1"))
        with self.assertRaisesRegex(KdenliveError, "locked"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_effects_rejected(self):
        project = self.mutate(lambda r: ET.SubElement(r.find("producer[@id='red']"), "filter", {"id": "grade"}))
        with self.assertRaisesRegex(KdenliveError, "effects"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_retiming_rejected(self):
        project = self.mutate(lambda r: setattr(r.find("producer[@id='red']/property[@name='mlt_service']"), "text", "timewarp"))
        with self.assertRaisesRegex(KdenliveError, "Retimed"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_user_composition_rejected(self):
        project = self.mutate(lambda r: setattr(r.find(f"tractor[@id='{SEQUENCE}']/transition/property[@name='internal_added']"), "text", "0"))
        with self.assertRaisesRegex(KdenliveError, "compositions"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_active_mix_lane_rejected(self):
        def add_entry(root):
            root.find("playlist[@id='empty_lane']").append(copy.deepcopy(root.find("playlist[@id='video_lane']/entry")))
        project = self.mutate(add_entry)
        with self.assertRaisesRegex(KdenliveError, "second playlist"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_unknown_entry_metadata_rejected(self):
        project = self.mutate(lambda r: setattr(ET.SubElement(r.find("playlist[@id='video_lane']/entry"), "property", {"name": "unknown:new"}), "text", "1"))
        with self.assertRaisesRegex(KdenliveError, "metadata"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_unknown_entry_attributes_rejected(self):
        project = self.mutate(lambda r: r.find("playlist[@id='video_lane']/entry").set("mix_in", "4"))
        with self.assertRaisesRegex(KdenliveError, "attributes"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_shared_tracks_rejected_for_edit(self):
        def duplicate(root):
            node = copy.deepcopy(root.find(f"tractor[@id='{SEQUENCE}']"))
            node.set("id", "second")
            node.find("property[@name='kdenlive:uuid']").text = "second"
            node.remove(node.find("transition"))
            root.insert(0, node)
        project = self.mutate(duplicate)
        with self.assertRaisesRegex(KdenliveError, "Shared timeline"):
            project.plan("split", {"instance_id": self.instance, "frame": 30})

    def test_source_changed_since_plan_rejected(self):
        plan = self.guide()
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        with self.assertRaisesRegex(KdenliveError, "changed"):
            self.project.apply(plan, self.folder / "new.kdenlive")
        self.assertFalse((self.folder / "new.kdenlive").exists())

    def test_tampered_plan_rejected(self):
        plan = self.guide()
        plan["summary"] = "fake approval"
        with self.assertRaisesRegex(KdenliveError, "modified"):
            self.project.apply(plan, self.folder / "new.kdenlive")

    def test_cancellation_leaves_no_output(self):
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(KdenliveError, "cancelled"):
            self.project.apply(self.guide(), self.folder / "new.kdenlive", event)
        self.assertFalse((self.folder / "new.kdenlive").exists())

    def test_existing_output_and_source_rejected(self):
        for output in (self.source, self.folder / "existing.kdenlive"):
            output.write_bytes(self.source.read_bytes())
            before = output.read_bytes()
            with self.assertRaisesRegex(KdenliveError, "overwriting"):
                self.project.apply(self.guide(), output)
            self.assertEqual(output.read_bytes(), before)

    def test_output_race_not_overwritten_and_temp_cleaned(self):
        output = self.folder / "race.kdenlive"
        original_link = os.link
        def race(src, dst):
            output.write_bytes(b"other writer")
            return original_link(src, dst)
        with patch("editing_copilot.kdenlive.os.link", side_effect=race):
            with self.assertRaisesRegex(KdenliveError, "appeared"):
                self.project.apply(self.guide(), output)
        self.assertEqual(output.read_bytes(), b"other writer")
        self.assertEqual(list(self.folder.glob(".editing-copilot-*")), [])

    def test_failure_during_publication_cleans_temp(self):
        with patch("editing_copilot.kdenlive.os.link", side_effect=OSError("unsupported filesystem")):
            with self.assertRaisesRegex(KdenliveError, "publish"):
                self.project.apply(self.guide(), self.folder / "new.kdenlive")
        self.assertEqual(list(self.folder.glob(".editing-copilot-*")), [])

    def test_dtd_entities_rejected(self):
        for data in (b'<!DOCTYPE mlt [<!ENTITY x "expanded">]><mlt>&x;</mlt>', b'<!doctype mlt><mlt/>', '<mlt/>'.encode("utf-16")):
            with self.subTest(data=data[:50]):
                with self.assertRaises(KdenliveError):
                    _parse(data)

    def test_xml_malformed_duplicate_property_and_complexity_rejected(self):
        for data in (b"<mlt>", b"<root/>", b'<mlt><property name="x">1</property><property name="x">2</property></mlt>', b"<mlt>" + b"<a>" * 130 + b"</a>" * 130 + b"</mlt>", b'<mlt><property name="x"><a/></property></mlt>'):
            with self.subTest(data=data[:50]):
                with self.assertRaises(KdenliveError):
                    _parse(data)

    def test_duplicate_id_and_dangling_producer_rejected(self):
        with self.assertRaises(KdenliveError):
            self.mutate(lambda r: r.append(copy.deepcopy(r.find("producer[@id='red']"))))
        with self.assertRaises(KdenliveError):
            self.mutate(lambda r: r.find("playlist[@id='video_lane']/entry").set("producer", "missing"))

    def test_fractional_rate_and_quantized_clock_times(self):
        def convert(root):
            profile = root.find("profile")
            profile.set("frame_rate_num", "30000")
            profile.set("frame_rate_den", "1001")
        project = self.mutate(convert)
        self.assertEqual(project.describe()["frame_rate"], {"numerator": 30000, "denominator": 1001})
        self.assertEqual(project._frames("00:00:01.001"), 30)
        self.assertEqual(project._frames("00:00:00.033"), 1)
        with self.assertRaises(KdenliveError):
            project._frames("00:00:00.020")

    def test_multiple_sequences_requires_explicit_guide_target(self):
        def duplicate(root):
            node = copy.deepcopy(root.find(f"tractor[@id='{SEQUENCE}']"))
            node.set("id", "second")
            node.find("property[@name='kdenlive:uuid']").text = "second"
            node.remove(node.find("transition"))
            root.insert(0, node)
        project = self.mutate(duplicate)
        with self.assertRaisesRegex(KdenliveError, "exact timeline"):
            self.guide(project)
        self.assertEqual(project.plan("add_guide", {"sequence_id": SEQUENCE, "frame": 12, "comment": "x"})["args"]["sequence_id"], SEQUENCE)

    def test_readonly_description_cannot_mutate_internal_state(self):
        description = self.project.describe()
        description["sequences"].clear()
        self.assertEqual(len(self.project.describe()["sequences"]), 1)


MLT_BIN = Path(os.environ.get("KDENLIVE_TEST_BIN", r"C:\Program Files\Kdenlive\bin"))


@unittest.skipUnless(all((MLT_BIN / name).is_file() for name in ("melt.exe", "ffmpeg.exe", "ffprobe.exe")),
                     "Kdenlive MLT/FFmpeg executables not installed; offline tests still run.")
class KdenliveRenderIntegrationTests(unittest.TestCase):
    """Headless render checks against actual installed MLT, using test cards only.

    These establish rendering correctness of the supported operations, not full
    Kdenlive GUI reopen compatibility. No user project is opened or modified.
    """
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.source = cls.folder / "source.kdenlive"
        cls.source.write_bytes(FIXTURE.read_bytes())
        cls.project = KdenliveProject(cls.source)
        cls.instance = cls.project.describe()["sequences"][0]["tracks"][0]["playlists"][0]["instances"][0]["instance_id"]
        cls.baseline = cls.render(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def render(cls, path):
        output = cls.folder / (path.stem + ".mkv")
        process = subprocess.run([str(MLT_BIN / "melt.exe"), "-silent", str(path), "-consumer", "avformat:" + str(output),
                                  "vcodec=ffv1", "acodec=pcm_s16le", "real_time=-1"],
                                 stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        if process.returncode:
            raise AssertionError(process.stderr.decode(errors="replace")[-2000:])
        probe = subprocess.run([str(MLT_BIN / "ffprobe.exe"), "-v", "error", "-select_streams", "v:0", "-count_frames",
                                "-show_entries", "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json", str(output)],
                               capture_output=True, check=True, timeout=10)
        details = json.loads(probe.stdout)["streams"][0]
        if details != {"width": 320, "height": 180, "r_frame_rate": "25/1", "nb_read_frames": "100"}:
            raise AssertionError(f"Wrong rendered output dimensions/frame count: {details}")
        raw = subprocess.run([str(MLT_BIN / "ffmpeg.exe"), "-v", "error", "-i", str(output), "-map", "0:v:0",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                             capture_output=True, check=True, timeout=10).stdout
        size = 320 * 180 * 3
        if len(raw) != size * 100:
            raise AssertionError("Raw decoded frame count mismatch.")
        return [raw[i * size:(i + 1) * size] for i in range(100)]

    def test_fixture_is_not_empty(self):
        self.assertNotEqual(self.baseline[0], self.baseline[10])
        self.assertEqual(self.baseline[10], self.baseline[40])
        self.assertEqual(self.baseline[0], self.baseline[60])

    def test_guide_preserves_all_rendered_pixels(self):
        output = self.folder / "guided.kdenlive"
        self.project.apply(self.project.plan("add_guide", {"frame": 12, "comment": "integration"}), output)
        self.assertEqual(self.render(output), self.baseline)

    def test_split_preserves_every_rendered_frame(self):
        output = self.folder / "split.kdenlive"
        self.project.apply(self.project.plan("split", {"instance_id": self.instance, "frame": 30}), output)
        self.assertEqual(self.render(output), self.baseline)

    def test_trim_changes_only_removed_intervals(self):
        output = self.folder / "trimmed.kdenlive"
        self.project.apply(self.project.plan("trim", {"instance_id": self.instance, "source_in": 20, "source_out_exclusive": 50}), output)
        actual = self.render(output)
        removed = set(range(5, 15)) | set(range(45, 55))
        for index, frame in enumerate(actual):
            with self.subTest(frame=index):
                self.assertEqual(frame, self.baseline[0] if index in removed else self.baseline[index])


if __name__ == "__main__":
    unittest.main()
