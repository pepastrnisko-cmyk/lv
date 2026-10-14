"""M2: grammar, voice routing and Controller wiring for the new Kdenlive project-copy edits."""
import hashlib, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from editing_copilot.commands import UnsupportedCommand, parse_command
from editing_copilot.kdenlive import KdenliveError
from editing_copilot.nlu import interpret
from editing_copilot.runtime import Controller

FIXTURE = Path(__file__).parent / "fixtures" / "simple.kdenlive"


class GrammarTests(unittest.TestCase):
    def test_new_commands(self):
        c = parse_command("add effect Gaussian blur to clip selected")
        self.assertEqual((c.operation, c.args), ("add_effect", {"effect": "Gaussian blur", "clip_id": "selected"}))
        self.assertEqual(parse_command('lock track "Video 1"').args, {"state": "lock", "track": "Video 1"})
        self.assertEqual(parse_command("show track V1").args, {"state": "unhide", "track": "V1"})
        self.assertEqual(parse_command("move clip selected to frame 0").args, {"clip_id": "selected", "frame": 0})
        self.assertEqual(parse_command("delete clip selected").operation, "delete_clip")
        self.assertEqual(parse_command("Remove clip abc").args, {"clip_id": "abc"})
        with self.assertRaises(UnsupportedCommand):
            parse_command("move clip selected to frame -4")

    def test_existing_grammar_unchanged(self):
        self.assertEqual(parse_command("split clip selected at frame 30").operation, "split_clip")
        self.assertEqual(parse_command("inspect project").operation, "inspect")
        with self.assertRaises(UnsupportedCommand):
            parse_command("make it cinematic")

    def test_voice_routing(self):
        self.assertEqual(interpret("add effect sepia to clip selected").value, "add effect sepia to clip selected")
        self.assertEqual(interpret("add effect sepia to clip selected").kind, "command")
        i = interpret("move the selected clip to 2 seconds", fps=25)
        self.assertEqual((i.kind, i.value), ("command", "move clip selected to frame 50"))
        self.assertEqual(interpret("lock track Video 1").kind, "command")
        self.assertEqual(interpret("delete clip selected").kind, "command")
        # existing behaviour preserved
        self.assertEqual(interpret("add effect Gaussian blur").kind, "workflow")
        self.assertEqual(interpret("delete clip").kind, "live")
        self.assertEqual(interpret("drag Intro to Video 2").kind, "ui")
        # Resolve: no on-screen effect workflow, so this now parses and the Controller refuses it for Resolve
        self.assertEqual(interpret("add effect sepia to clip selected", editor="resolve").kind, "command")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "s.kdenlive"; self.src.write_bytes(FIXTURE.read_bytes())
        self.c = Controller(self.dir / "data"); self.addCleanup(self.c.close)
        self.c.select("kdenlive", self.src)
        snap = self.c.inspect()
        self.first = snap["sequences"][0]["tracks"][0]["playlists"][0]["instances"][0]["instance_id"]

    def roundtrip(self, text, selected=None):
        original = hashlib.sha256(self.src.read_bytes()).hexdigest()
        plan = self.c.plan(text, selected_instance=selected)
        result = self.c.apply(selected_instance=selected, expected_text=text)
        self.assertEqual(result["verification"], "structural_readback_passed")
        self.assertTrue(Path(result["output"]).is_file())
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), original)
        undone = self.c.undo()
        self.assertEqual(undone["path"], str(self.src.resolve()))
        return plan, result

    def test_effect_track_move_delete_with_undo(self):
        self.roundtrip("add effect sepia to clip selected", self.first)
        self.roundtrip('lock track "Video 1"')
        self.roundtrip("hide track video 1")
        self.roundtrip("move clip selected to frame 0", self.first)
        plan, _ = self.roundtrip("delete clip selected", self.first)
        self.assertTrue(plan["requires_confirmation"])
        self.assertIn("DELETE", plan["summary"])

    def test_errors_and_selection(self):
        with self.assertRaises(ValueError):
            self.c.plan("delete clip selected")  # nothing selected
        with self.assertRaises(ValueError):
            self.c.plan("lock track Nope")
        with self.assertRaises(KdenliveError):
            self.c.plan("add effect lua to clip selected", selected_instance=self.first)


class VoiceConfirmTests(unittest.TestCase):
    def test_voice_apply_on_delete_requires_confirm(self):
        try:
            from editing_copilot.ui import CopilotApp
        except Exception as exc:  # tkinter unavailable
            self.skipTest(f"ui import unavailable: {exc}")
        def stub(plan):
            return SimpleNamespace(voice_state=MagicMock(), _overlay_set=MagicMock(), speaker=MagicMock(), status=MagicMock(),
                                   controller=SimpleNamespace(preview={"plan": plan}), _executor=None, _busy=False,
                                   config={"voice": {"allow_voice_apply": True}}, apply_button=MagicMock(**{"cget.return_value": "normal"}),
                                   apply_preview=MagicMock(), stop=MagicMock())
        intent = interpret("apply")
        s = stub({"operation": "delete_clip", "requires_confirmation": True})
        CopilotApp._handle_voice(s, "intent", intent)
        s.apply_preview.assert_not_called()
        CopilotApp._handle_voice(s, "intent", interpret("confirm"))
        s.apply_preview.assert_called_once()
        s2 = stub({"operation": "add_guide"})
        CopilotApp._handle_voice(s2, "intent", intent)
        s2.apply_preview.assert_called_once()


if __name__ == "__main__":
    unittest.main()
