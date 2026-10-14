"""Baseline: behaviours of the ORIGINAL 0.1.0 adapter that must survive hardening."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from editing_copilot.resolve import ResolveAdapter, ResolveError
from resolve_fakes import FakeResolve


class Baseline(unittest.TestCase):
    def setUp(self):
        self.r = FakeResolve(); self.a = ResolveAdapter(self.r); self.tl = self.r.timeline

    def test_plan_apply_undo_roundtrip(self):
        plan = self.a.plan("add_marker", {"frame": 10, "name": "A"})
        tx = self.a.apply(plan)
        self.assertEqual(tx["status"], "applied"); self.assertIn(10, self.tl.markers)
        self.assertEqual(self.a.undo(tx)["status"], "undone"); self.assertNotIn(10, self.tl.markers)

    def test_existing_marker_never_overwritten(self):
        self.tl.markers[10] = {"color": "Red", "name": "mine", "note": "", "duration": 1, "customData": ""}
        with self.assertRaises(ResolveError) as c: self.a.plan("add_marker", {"frame": 10})
        self.assertEqual(c.exception.code, "marker_conflict")

    def test_silent_corruption_not_reported_success(self):
        self.tl.silent_corrupt = True
        with self.assertRaises(ResolveError) as c: self.a.apply(self.a.plan("add_marker", {"frame": 5}))
        self.assertEqual(c.exception.code, "verification_failed")

    def test_rejects_bool_and_float_frames(self):
        for bad in (True, 1.5, "3"):
            with self.assertRaises(ResolveError): self.a.plan("add_marker", {"frame": bad})

    def test_busy_editor_blocks(self):
        self.r.project.rendering = True
        with self.assertRaises(ResolveError) as c: self.a.plan("add_marker", {"frame": 1})
        self.assertEqual(c.exception.code, "editor_busy")

    def test_timeline_change_makes_plan_stale(self):
        plan = self.a.plan("add_marker", {"frame": 1}); self.tl.uid = "tl-2"
        with self.assertRaises(ResolveError) as c: self.a.apply(plan)
        self.assertEqual(c.exception.code, "stale_plan")

    def test_apply_is_idempotent(self):
        plan = self.a.plan("add_marker", {"frame": 3}); self.a.apply(plan)
        self.assertTrue(self.a.apply(plan).get("idempotent")); self.assertEqual(len(self.tl.add_calls), 1)

    def test_changed_marker_not_removed(self):
        plan = self.a.plan("add_marker", {"frame": 3}); tx = self.a.apply(plan)
        self.tl.markers[3]["name"] = "user edited"
        with self.assertRaises(ResolveError) as c: self.a.undo(tx)
        self.assertEqual(c.exception.code, "undo_conflict")


if __name__ == "__main__":
    unittest.main()
