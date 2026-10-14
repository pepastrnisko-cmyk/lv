"""Common editor interface: thin delegation, no behaviour change."""
import shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_fakes import FakeResolve
from editing_copilot.editors import (EditorAdapter, KdenliveEditor, ResolveEditor, UnsupportedEditorOperation, open_editor)
from editing_copilot.kdenlive import KdenliveError, KdenliveProject
from editing_copilot.resolve import ResolveAdapter, ResolveError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "simple.kdenlive"


class KdenliveEditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "p.kdenlive"; shutil.copyfile(FIXTURE, self.path)

    def test_conforms_and_describe_matches_direct(self):
        editor = open_editor("kdenlive", self.path)
        self.assertIsInstance(editor, EditorAdapter)
        self.assertEqual(editor.describe(), KdenliveProject(self.path).describe())
        self.assertTrue(editor.supports("add_guide")); self.assertFalse(editor.supports("add_marker"))

    def test_plan_and_apply_match_direct_and_keep_source(self):
        before = self.path.read_bytes()
        args = {"frame": 10, "comment": "Intro"}
        direct = KdenliveProject(self.path).plan("add_guide", dict(args))
        editor = KdenliveEditor(self.path)
        plan = editor.plan("add_guide", dict(args))
        self.assertEqual(plan, direct)
        out_a, out_b = Path(self.tmp.name) / "a.kdenlive", Path(self.tmp.name) / "b.kdenlive"
        KdenliveProject(self.path).apply(direct, out_a)
        editor.apply(plan, output=out_b)
        self.assertEqual(out_a.read_bytes(), out_b.read_bytes())
        self.assertEqual(self.path.read_bytes(), before)

    def test_errors_are_the_same_type(self):
        with self.assertRaises(KdenliveError):
            KdenliveEditor(self.path).plan("add_guide", {"frame": -1, "comment": "x"})
        with self.assertRaises(UnsupportedEditorOperation):
            KdenliveEditor(self.path).undo({})

    def test_unknown_editor_rejected(self):
        with self.assertRaises(ValueError):
            open_editor("premiere")
        with self.assertRaises(ValueError):
            KdenliveEditor()


class ResolveEditorTests(unittest.TestCase):
    def test_marker_roundtrip_matches_adapter(self):
        fake = FakeResolve()
        editor = open_editor("resolve", fake)
        self.assertIsInstance(editor, EditorAdapter)
        self.assertEqual(editor.describe(), ResolveAdapter(fake).describe())
        self.assertEqual(editor.probe()["mutation_enabled"], True)
        plan = editor.plan("add_marker", {"frame": 12, "name": "Hi"})
        tx = editor.apply(plan)
        self.assertEqual(fake.timeline.markers[12]["name"], "Hi")
        editor.undo(tx)
        self.assertNotIn(12, fake.timeline.markers)

    def test_wraps_existing_adapter_and_errors(self):
        adapter = ResolveAdapter(FakeResolve())
        editor = ResolveEditor(adapter=adapter)
        self.assertIs(editor.adapter, adapter)
        with self.assertRaises(ResolveError):
            editor.plan("split", {})


if __name__ == "__main__":
    unittest.main()
