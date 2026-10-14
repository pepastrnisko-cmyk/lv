import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from editing_copilot import config, workflows
from editing_copilot.actions import Executor
from editing_copilot.feedback import Speaker, set_start_with_windows
from editing_copilot.nlu import interpret
from editing_copilot.runtime import Controller
from editing_copilot.ui import CopilotApp
from tests.test_ui_actions import MockBackend

RES = Path(__file__).resolve().parents[1] / "resources"


class WorkflowTests(unittest.TestCase):
    def test_kdenlive_effect_flow(self):
        i = interpret("add effect gaussian blur", editor="kdenlive")
        actions, destructive = i.data
        self.assertEqual(i.kind, "workflow"); self.assertFalse(destructive)
        self.assertEqual([a.kind for a in actions], ["click", "wait", "click", "key", "type", "wait", "click"])
        self.assertTrue(actions[-1].double)

    def test_render_is_confirmed_and_never_starts(self):
        b = MockBackend(uia=[])
        ex = Executor(b, config.load_config(Path(tempfile.mkdtemp()))[0])
        i = interpret("open render dialog with preset MP4", editor="kdenlive")
        r = ex.request("kdenlive", i.data[0], i.value, confirm=i.data[1])
        self.assertEqual(r["outcome"], "needs_confirmation"); self.assertEqual(b.calls, [])
        self.assertIn("does not start", i.value)

    def test_resolve_pages_and_nodes(self):
        b = MockBackend()
        ex = Executor(b, config.load_config(Path(tempfile.mkdtemp()))[0])
        for text, key in (("go to color page", "shift+6"), ("switch to the edit page", "shift+4"), ("add parallel node", "alt+p")):
            with self.subTest(text=text):
                i = interpret(text, editor="resolve")
                ex.request("resolve", i.data[0], i.value, confirm=i.data[1])
                self.assertIn(("key", key), b.calls)
        self.assertTrue(interpret("reset grade", editor="resolve").data[1])

    def test_existing_grammar_untouched(self):
        self.assertEqual(interpret("add guide at frame 10 named A").kind, "command")
        self.assertEqual(interpret("add a marker at 3 seconds named X", editor="resolve").kind, "command")
        self.assertEqual(interpret("play").kind, "live")

    def test_cheatsheet_lists_everything(self):
        for phrase in ("click Render", "drag Intro", "record macro", "add effect", "color page", "how do I"):
            self.assertIn(phrase, workflows.CHEATSHEET)


class AppFeatureTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.root = tk.Tk(); self.root.withdraw()
        self.app = CopilotApp(self.root, Controller(self.dir), RES, load_demo=False, enable_hotkey=False)

    def tearDown(self):
        self.app.close()
        try: self.root.destroy()
        except tk.TclError: pass

    def test_overlay_cheatsheet_wizard(self):
        self.app.toggle_overlay(True); self.app._overlay_set(heard="copilot play", result="Done", listening="● Listening")
        self.assertEqual(self.app._ov_heard.get(), "Heard: copilot play")
        self.app.open_cheatsheet()
        from editing_copilot.wizard import SetupWizard
        w = SetupWizard(self.app)
        w.mode.set("local"); w.feedback.set("off"); w.listen.set(False); w.startup.set(False)
        with patch("editing_copilot.ui.set_user_env") as env:
            w.key.set("gsk_test"); w.finish()
            env.assert_called_once_with("GROQ_API_KEY", "gsk_test")
        saved, _ = config.load_config(self.dir)
        self.assertEqual(saved["mode"], "local"); self.assertTrue(saved["ui"]["first_run_done"])
        self.assertNotIn("gsk_test", (self.dir / "config.json").read_text())

    def test_speaker_off_is_silent(self):
        Speaker("off").say("x")  # no exception, no thread

    def test_startup_disable_safe(self):
        self.assertFalse(set_start_with_windows(False))


class AlternativeLabelTests(unittest.TestCase):
    def test_first_existing_alternative_used(self):
        from editing_copilot.uiauto import Target
        b = MockBackend(uia=[Target("Sequence", "MenuItem", (0, 0, 80, 20))])
        ex = Executor(b, config.load_config(Path(tempfile.mkdtemp()))[0])
        ex.request("kdenlive", [__import__("editing_copilot.actions", fromlist=["Action"]).Action("click", label="Project|Sequence", role="menu")])
        self.assertIn(("invoke", "Sequence"), b.calls)


class TypedEchoTests(unittest.TestCase):
    def test_result_below_search_field_is_clicked_not_the_field_text(self):
        from editing_copilot.uiauto import Target
        from editing_copilot.actions import Action
        b = MockBackend(uia=[], ocr=[Target("Search", "Text", (0, 100, 60, 120), "ocr"),
                                     Target("gaussian blur", "Text", (70, 100, 160, 120), "ocr"),
                                     Target("Gaussian Blur", "Text", (10, 200, 120, 220), "ocr")])
        ex = Executor(b, config.load_config(Path(tempfile.mkdtemp()))[0])
        ex.request("kdenlive", [Action("click", label="Search", role="field"), Action("type", text="gaussian blur"),
                                Action("click", label="gaussian blur", role="item", double=True)])
        self.assertIn(("click", 65, 210, "left", True, ""), b.calls)
