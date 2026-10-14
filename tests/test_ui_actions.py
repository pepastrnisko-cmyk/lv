import tempfile
import threading
import unittest
from pathlib import Path

from editing_copilot import config
from editing_copilot.actions import Action, ActionError, Executor, MacroStore
from editing_copilot.knowledge import KnowledgeBase
from editing_copilot.nlu import interpret
from editing_copilot.uiauto import Target, match_score, normalize_label, rank

RES = Path(__file__).resolve().parents[1] / "resources"


class MockBackend:
    def __init__(self, focused=True, uia=None, ocr=None):
        self.focused, self.calls = focused, []
        self.uia = uia if uia is not None else [Target("&File", "MenuItem", (0, 0, 40, 20)),
                                                Target("Render... (Ctrl+Return)", "Button", (100, 0, 180, 20)),
                                                Target("Intro", "ListItem", (10, 100, 110, 120)),
                                                Target("Intro", "ListItem", (10, 200, 110, 220)),
                                                Target("Video 2", "Pane", (0, 300, 800, 340))]
        self.ocr = ocr or []

    def focus_editor(self, editor): self.calls.append(("focus", editor)); return self.focused
    def editor_window(self, editor): return 1 if self.focused else None
    def uia_controls(self, hwnd): return list(self.uia)
    def ocr_controls(self, hwnd): self.calls.append(("ocr",)); return list(self.ocr)
    def invoke(self, t): self.calls.append(("invoke", t.name)); return True
    def click(self, x, y, button="left", double=False, modifiers=""): self.calls.append(("click", x, y, button, double, modifiers))
    def drag(self, s, e, button="left", modifiers=""): self.calls.append(("drag", s, e, modifiers))
    def move(self, x, y): self.calls.append(("move", x, y))
    def key(self, spec): self.calls.append(("key", spec))
    def type_text(self, t): self.calls.append(("type", t))
    def scroll(self, n): self.calls.append(("scroll", n))


def cfg():
    return config.load_config(Path(tempfile.mkdtemp()))[0]


def run(text, backend=None, editor="kdenlive"):
    b = backend or MockBackend()
    ex = Executor(b, cfg(), MacroStore(Path(tempfile.mkdtemp()) / "m.json"))
    intent = interpret(text, editor=editor)
    return ex, b, intent, ex.request(editor, intent.data) if intent.kind == "ui" else None


class MatchingTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_label("&File"), "file")
        self.assertEqual(normalize_label("<h3>Welcome to Kdenlive</h3>"), "welcome to kdenlive")
        self.assertEqual(normalize_label("Render... (Ctrl+Return)"), "render")
        self.assertGreater(match_score("render", "Render..."), 0.95)
        self.assertLess(match_score("render", "Timeline"), 0.5)

    def test_role_preference(self):
        c = [Target("Edit", "MenuItem", (0, 0, 1, 1)), Target("Edit", "TabItem", (0, 50, 1, 51))]
        self.assertEqual(rank("edit", c, "tab")[0].role, "TabItem")


class ExecutorTests(unittest.TestCase):
    def test_click_menu_invokes_uia(self):
        _, b, i, r = run("open File menu")
        self.assertEqual(r["outcome"], "sent_unverified")
        self.assertIn(("invoke", "&File"), b.calls)

    def test_right_and_double_click_use_mouse(self):
        _, b, _, _ = run("right click Video 2")
        self.assertIn(("click", 400, 320, "right", False, ""), b.calls)
        _, b, _, _ = run("double click Video 2")
        self.assertIn(("click", 400, 320, "left", True, ""), b.calls)

    def test_modifier_and_ordinal(self):
        _, b, _, _ = run("shift click the second Intro")
        self.assertIn(("click", 60, 210, "left", False, "shift"), b.calls)

    def test_drag(self):
        _, b, _, _ = run("drag Intro to Video 2")
        self.assertIn(("drag", (60, 110), (400, 320), ""), b.calls)
        _, b, _, _ = run("drag from 10 20 to 30 40")
        self.assertIn(("drag", (10, 20), (30, 40), ""), b.calls)
        _, b, _, _ = run("drag Intro right 50 pixels")
        self.assertIn(("drag", (60, 110), (110, 110), ""), b.calls)

    def test_ocr_fallback(self):
        b = MockBackend(uia=[], ocr=[Target("Color", "Text", (500, 900, 560, 920), "ocr")])
        _, b, _, r = run("click the Color tab", b, "resolve")
        self.assertIn(("ocr",), b.calls)
        self.assertIn(("click", 530, 910, "left", False, ""), b.calls)

    def test_not_found_clicks_nothing(self):
        with self.assertRaises(ActionError):
            run("click Nonexistent Thing")

    def test_focus_required(self):
        b = MockBackend(focused=False)
        with self.assertRaises(ActionError):
            run("click File", b)
        self.assertFalse([c for c in b.calls if c[0] in ("click", "invoke")])

    def test_destructive_needs_confirmation(self):
        ex, b, _, r = run("click Render")
        self.assertEqual(r["outcome"], "needs_confirmation")
        self.assertFalse([c for c in b.calls if c[0] in ("click", "invoke")])
        self.assertEqual(ex.confirm()["outcome"], "sent_unverified")
        self.assertTrue([c for c in b.calls if c[0] == "invoke"])
        ex2, b2, _, r2 = run("press delete")
        self.assertEqual(r2["outcome"], "needs_confirmation")
        self.assertTrue(ex2.cancel()); self.assertIsNone(ex2.confirm())
        self.assertFalse([c for c in b2.calls if c[0] == "key"])

    def test_keys_type_scroll(self):
        for text, call in (("press control shift z", ("key", "ctrl+shift+z")), ("type Hello World", ("type", "Hello World")),
                           ("scroll down 2", ("scroll", -2)), ("close dialog", ("key", "escape"))):
            with self.subTest(text=text):
                _, b, _, _ = run(text)
                self.assertIn(call, b.calls)

    def test_stop_aborts_between_steps(self):
        b = MockBackend()
        ex = Executor(b, cfg())
        steps = [Action("key", text="a"), Action("wait", seconds=5), Action("key", text="b")]
        threading.Timer(0.2, ex.stop_event.set).start()
        r = ex.request("kdenlive", steps)
        self.assertEqual(r["outcome"], "cancelled")
        self.assertNotIn(("key", "b"), b.calls)


class MacroTests(unittest.TestCase):
    def test_record_and_run(self):
        b = MockBackend()
        store = MacroStore(Path(tempfile.mkdtemp()) / "macros.json")
        ex = Executor(b, cfg(), store)
        ex.start_recording("kdenlive", "My Export")
        for t in ("open File menu", "press ctrl+s", "play"):
            i = interpret(t)
            ex.request("kdenlive", i.data if i.kind == "ui" else [Action("live", text=i.value)])
        self.assertIn("3 step", ex.stop_recording())
        reloaded = MacroStore(store.path)
        self.assertEqual(len(reloaded.get("kdenlive", "my export")), 3)
        b.calls.clear()
        self.assertEqual(ex.run_macro("kdenlive", "my  export")["outcome"], "sent_unverified")
        self.assertIn(("key", "space"), b.calls)

    def test_macro_with_destructive_step_confirms_up_front(self):
        b = MockBackend()
        store = MacroStore(Path(tempfile.mkdtemp()) / "m.json")
        store.put("kdenlive", "clean", [Action("key", text="ctrl+a"), Action("key", text="delete")])
        ex = Executor(b, cfg(), store)
        self.assertEqual(ex.run_macro("kdenlive", "clean")["outcome"], "needs_confirmation")
        self.assertEqual(b.calls, [])

    def test_invalid_file_entries_reported(self):
        p = Path(tempfile.mkdtemp()) / "m.json"
        p.write_text('{"kdenlive": {"bad": [{"kind": "explode"}], "ok": [{"kind": "key", "text": "ctrl+s"}]}}')
        s = MacroStore(p)
        self.assertEqual(s.names("kdenlive"), ["ok"]); self.assertTrue(s.errors)

    def test_voice_intents(self):
        self.assertEqual(interpret("record macro my export").data, ("record", "my export"))
        self.assertEqual(interpret("stop recording").kind, "macro")
        self.assertEqual(interpret("run macro my export").data, ("run", "my export"))


class KnowledgeTests(unittest.TestCase):
    kb = KnowledgeBase(RES / "knowledge" / "kdenlive_grading_master_reference.md")

    def test_loaded(self):
        self.assertGreater(len(self.kb.sections), 40)

    def test_routing(self):
        self.assertTrue(self.kb.search("ripple trim")[0].title.startswith("K2"))
        self.assertTrue(self.kb.search("render export settings")[0].title.startswith("K9"))
        self.assertTrue(self.kb.search("set up proxies")[0].title.startswith("K8"))
        self.assertTrue(self.kb.search("add subtitles")[0].title.startswith("K6"))

    def test_help_intent_and_answer(self):
        i = interpret("how do I match skin tones between shots")
        self.assertEqual(i.kind, "help")
        r = self.kb.answer(i.data, {}, ask=lambda c, q, s: "1. Confirm on screen.")
        self.assertTrue(r["sections"]); self.assertIn("answer", r)


if __name__ == "__main__":
    unittest.main()


class CliTests(unittest.TestCase):
    def test_interpret_cli_serializes_ui(self):
        import os, subprocess, sys, json as _j
        env = dict(os.environ, PYTHONPATH=str(RES.parent / "src"), EDITING_COPILOT_DATA_DIR=tempfile.mkdtemp())
        out = subprocess.run([sys.executable, "-m", "editing_copilot", "--interpret", "click Render"], env=env,
                             capture_output=True, text=True, check=True).stdout
        d = _j.loads(out)
        self.assertEqual(d["data"][0]["label"], "Render"); self.assertTrue(d["needs_confirmation"])
        for text in ("add effect gaussian blur", "open render dialog", "record macro x", "how do I trim", "play"):
            out = subprocess.run([sys.executable, "-m", "editing_copilot", "--interpret", text], env=env,
                                 capture_output=True, text=True, check=True).stdout
            self.assertTrue(_j.loads(out)["kind"])
