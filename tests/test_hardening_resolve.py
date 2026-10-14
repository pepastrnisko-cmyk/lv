"""Tests for 0.1.1 adapter hardening."""
import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from editing_copilot.resolve import ResolveAdapter, ResolveError, is_pre_mutation, PRE_MUTATION_CODES
from resolve_fakes import FakeResolve, FakeTimeline, FakeItem


class Hardening(unittest.TestCase):
    def setUp(self):
        self.r = FakeResolve(); self.a = ResolveAdapter(self.r); self.tl = self.r.timeline

    def test_probe_reports_mutation_enabled(self):
        probe = self.a.probe()
        self.assertTrue(probe["mutation_enabled"]); self.assertEqual(probe["missing_timeline_api"], [])

    def test_missing_api_disables_editing_with_clear_error(self):
        del FakeTimeline.AddMarker
        try:
            with self.assertRaises(ResolveError) as c: self.a.plan("add_marker", {"frame": 1})
            self.assertEqual(c.exception.code, "api_unavailable"); self.assertIn("AddMarker", str(c.exception))
            self.assertFalse(self.a.probe()["mutation_enabled"])
        finally:
            from resolve_fakes import FakeTimeline as T
            def AddMarker(self, frame, color, name, note, duration, custom):
                self.add_calls.append((frame, color, name, note, duration, custom))
                if self.fail_add or frame in self.markers: return False
                self.markers[frame] = {"color": color, "name": "WRONG" if self.silent_corrupt else name,
                                       "note": note, "duration": duration, "customData": custom}
                self._add_count += 1; return True
            T.AddMarker = AddMarker

    def test_control_characters_rejected_in_name_but_note_allows_newlines(self):
        for bad in ("a\nb", "a\x07b", "tab\there"):
            with self.assertRaises(ResolveError): self.a.plan("add_marker", {"frame": 1, "name": bad})
        self.a.plan("add_marker", {"frame": 1, "note": "line1\nline2\tok"})
        with self.assertRaises(ResolveError): self.a.plan("add_marker", {"frame": 1, "note": "bell\x07"})

    def test_pre_mutation_classification(self):
        self.assertTrue(is_pre_mutation(ResolveError("stale_plan", "x")))
        self.assertFalse(is_pre_mutation(ResolveError("verification_failed", "x")))
        self.assertFalse(is_pre_mutation(ResolveError("readback_failed", "x")))
        self.assertFalse(is_pre_mutation(ValueError("x")))
        self.assertNotIn("verification_failed", PRE_MUTATION_CODES)

    def test_every_pre_mutation_code_really_precedes_the_host_call(self):
        # Stale plan after a timeline swap: AddMarker must never be called.
        plan = self.a.plan("add_marker", {"frame": 4}); self.tl.uid = "other"
        with self.assertRaises(ResolveError) as c: self.a.apply(plan)
        self.assertTrue(is_pre_mutation(c.exception)); self.assertEqual(self.tl.add_calls, [])

    def test_unknown_outcome_codes_are_not_pre_mutation(self):
        self.tl.silent_corrupt = True
        with self.assertRaises(ResolveError) as c: self.a.apply(self.a.plan("add_marker", {"frame": 4}))
        self.assertFalse(is_pre_mutation(c.exception))
        self.tl.silent_corrupt = False

    def test_readback_failure_after_add_is_unknown_not_success(self):
        self.tl.break_readback_after_add = True
        with self.assertRaises(ResolveError) as c: self.a.apply(self.a.plan("add_marker", {"frame": 4}))
        self.assertEqual(c.exception.code, "verification_failed"); self.assertIn(4, self.tl.markers)

    def test_describe_is_json_safe_with_items(self):
        self.tl.items["video"][0] = [FakeItem("i1", "Shot", 0, 48)]
        snap = self.a.describe(); json.dumps(snap)
        self.assertEqual(snap["clips"][0]["duration_frames"], 48)
        self.assertIn("capability_probe", snap)

    def test_describe_item_failure_names_the_track(self):
        class Bad(FakeItem):
            def GetName(self): raise RuntimeError("boom")
        self.tl.items["video"][0] = [Bad("i2", "x", 0, 1)]
        with self.assertRaises(ResolveError) as c: self.a.describe()
        self.assertEqual(c.exception.code, "readback_failed"); self.assertIn("video track 1", str(c.exception))

    def test_describe_rejects_non_list_item_list(self):
        self.tl.GetItemListInTrack = lambda k, i: "oops"
        with self.assertRaises(ResolveError): self.a.describe()

    def test_inverted_timeline_range_rejected(self):
        self.tl.start, self.tl.end = 100, 50
        with self.assertRaises(ResolveError) as c: self.a.describe()
        self.assertEqual(c.exception.code, "readback_failed")

    def test_undo_of_marker_that_vanished_is_idempotent(self):
        tx = self.a.apply(self.a.plan("add_marker", {"frame": 9})); del self.tl.markers[9]
        self.assertTrue(self.a.undo(tx)["idempotent"])

    def test_failed_delete_is_not_reported_as_undone(self):
        tx = self.a.apply(self.a.plan("add_marker", {"frame": 9})); self.tl.fail_delete = True
        with self.assertRaises(ResolveError) as c: self.a.undo(tx)
        self.assertEqual(c.exception.code, "verification_failed"); self.assertIn(9, self.tl.markers)

    def test_unknown_args_and_bad_color_rejected(self):
        with self.assertRaises(ResolveError): self.a.plan("add_marker", {"frame": 1, "evil": 1})
        with self.assertRaises(ResolveError): self.a.plan("add_marker", {"frame": 1, "color": "Teal"})
        with self.assertRaises(ResolveError): self.a.plan("delete_everything", {})

    def test_out_of_range_and_duration(self):
        for kw in ({"frame": 240}, {"frame": -1}, {"frame": 239, "duration": 2}, {"frame": 1, "duration": 0}):
            with self.assertRaises(ResolveError): self.a.plan("add_marker", kw)


if __name__ == "__main__":
    unittest.main()
