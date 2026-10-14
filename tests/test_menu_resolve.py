"""Menu-script tests with a fake Fusion UIManager (no Resolve required)."""
import importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / "resources" / "integration"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_fakes import FakeResolve


class Item:
    def __init__(self, props): self.__dict__.update(props); self.Text = props.get("Text", ""); self.PlainText = props.get("PlainText", ""); self.Enabled = props.get("Enabled", True)

class Handlers:
    def __setattr__(self, k, v): self.__dict__[k] = v

class Window:
    def __init__(self, tree):
        self.items, self.On = {}, {}
        self._collect(tree)
    def _collect(self, node):
        if isinstance(node, dict) and "kind" in node:
            if "ID" in node["props"]: self.items[node["props"]["ID"]] = Item(node["props"])
            for child in node.get("children", []): self._collect(child)
    def GetItems(self): return self.items
    def Show(self): pass
    def Hide(self): pass
    def Raise(self): pass

class OnMap(dict):
    def __missing__(self, key): self[key] = Handlers(); return self[key]

class UI:
    def _mk(kind):
        def make(self, a, b=None):
            if b is None: a, b = {}, a
            return {"kind": kind, "props": a, "children": b if isinstance(b, list) else []}
        return make
    VGroup = _mk("v"); HGroup = _mk("h")
    def Label(self, p): return {"kind": "l", "props": p}
    def LineEdit(self, p): return {"kind": "e", "props": p}
    def Button(self, p): return {"kind": "b", "props": p}
    def TextEdit(self, p): return {"kind": "t", "props": p}
    def FindWindow(self, _id): return None

class Dispatcher:
    script = None
    def __init__(self, ui): self.window = None
    def AddWindow(self, props, tree):
        self.window = Window(tree); self.window.On = OnMap(); Dispatcher.last = self; return self.window
    def RunLoop(self):
        if Dispatcher.script: Dispatcher.script(self.window)
    def ExitLoop(self): pass

class Bmd:
    UIDispatcher = Dispatcher

class Fusion:
    UIManager = UI()


def load_menu(tmp):
    os.environ["LOCALAPPDATA"] = tmp
    spec = importlib.util.spec_from_file_location("ec_menu", str(ROOT.parents[1] / "integrations" / "resolve" / "Editing Copilot.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.mod = load_menu(self.tmp)
        self.resolve = FakeResolve(); self.tl = self.resolve.timeline
        self.hist = Path(self.tmp) / "EditingCopilot" / "resolve-menu-history.json"

    def run_menu(self, script):
        Dispatcher.script = script
        self.mod.main({"resolve": self.resolve, "fusion": Fusion(), "bmd": Bmd()})

    def click(self, w, name): getattr(w.On[name], "Clicked")(None)
    def saved(self): return json.loads(self.hist.read_text(encoding="utf-8"))["transactions"]

    def test_preview_apply_undo(self):
        def s(w):
            i = w.GetItems(); i["Frame"].Text = "12"; i["Name"].Text = "Hello"; i["Color"].Text = "Blue"; i["Duration"].Text = "3"
            self.click(w, "Preview"); self.assertTrue(i["Apply"].Enabled)
            self.click(w, "Apply"); self.assertTrue(i["Output"].PlainText.startswith("VERIFIED"))
            self.assertEqual(self.tl.markers[12]["color"], "Blue"); self.assertEqual(self.tl.markers[12]["duration"], 3)
            e = self.saved()[-1]; self.assertEqual(e["status"], "applied"); self.assertIn("created_utc", e); self.assertIn("updated_utc", e)
            self.click(w, "Undo"); self.assertNotIn(12, self.tl.markers); self.assertEqual(self.saved()[-1]["status"], "undone")
        self.run_menu(s)

    def test_edited_fields_after_preview_block_apply(self):
        def s(w):
            i = w.GetItems(); i["Frame"].Text = "5"; self.click(w, "Preview"); i["Name"].Text = "changed"
            self.click(w, "Apply"); self.assertIn("changed after preview", i["Output"].PlainText); self.assertEqual(self.tl.markers, {})
        self.run_menu(s)

    def test_stale_plan_is_cancelled_in_history_and_says_no_change(self):
        def s(w):
            i = w.GetItems(); i["Frame"].Text = "5"; self.click(w, "Preview"); self.tl.uid = "swapped"
            self.click(w, "Apply")
            self.assertIn("No change was made", i["Output"].PlainText); self.assertEqual(self.tl.markers, {})
            self.assertEqual(self.saved()[-1]["status"], "cancelled")
        self.run_menu(s)

    def test_unknown_outcome_stays_pending_and_is_labelled(self):
        def s(w):
            i = w.GetItems(); i["Frame"].Text = "5"; self.tl.silent_corrupt = True
            self.click(w, "Preview"); self.click(w, "Apply")
            self.assertIn("UNKNOWN", i["Output"].PlainText); self.assertEqual(self.saved()[-1]["status"], "pending")
            self.tl.silent_corrupt = False
        self.run_menu(s)

    def test_history_must_be_durable_before_host_is_touched(self):
        def s(w):
            i = w.GetItems(); i["Frame"].Text = "5"; self.click(w, "Preview")
            def boom(*a, **k): raise OSError("disk full")
            self.mod._write_history = boom
            self.click(w, "Apply")
            self.assertEqual(self.tl.add_calls, []); self.assertEqual(self.tl.markers, {})
        self.run_menu(s)

    def test_bad_inputs_report_without_touching_project(self):
        def s(w):
            i = w.GetItems()
            for field, value in (("Frame", "-1"), ("Frame", "1.5"), ("Frame", "٣"), ("Duration", "0"), ("Color", "Teal")):
                i["Frame"].Text, i["Duration"].Text, i["Color"].Text = "5", "1", "Green"; i[field].Text = value
                self.click(w, "Preview"); self.assertFalse(i["Apply"].Enabled, (field, value))
            self.assertEqual(self.tl.markers, {})
        self.run_menu(s)

    def test_damaged_history_blocks_edits(self):
        self.hist.parent.mkdir(parents=True); self.hist.write_text("{not json", encoding="utf-8")
        def s(w):
            i = w.GetItems(); self.click(w, "Preview"); self.assertFalse(i["Apply"].Enabled)
        try: self.run_menu(s)
        except Exception: pass   # damaged history is surfaced; either path must leave the project untouched
        self.assertEqual(self.tl.markers, {}); self.assertEqual(self.hist.read_text(encoding="utf-8"), "{not json")

    def test_prune_never_drops_pending_or_applied(self):
        entries = [{"status": "pending", "id": "p"}] + [{"status": "undone", "id": str(n)} for n in range(700)] + [{"status": "applied", "id": "a"}]
        out = self.mod._prune(entries)
        self.assertLessEqual(len(out), 500); ids = {e["id"] for e in out}
        self.assertIn("p", ids); self.assertIn("a", ids)

    def test_no_uimanager_falls_back_read_only(self):
        class NoFusion: UIManager = None
        Dispatcher.script = None
        self.mod.main({"resolve": self.resolve, "fusion": NoFusion(), "bmd": Bmd()})
        self.assertEqual(self.tl.markers, {})

    def test_no_network_or_exec_in_scripts(self):
        for f in (ROOT.parents[1] / "integrations" / "resolve" / "Editing Copilot.py", ROOT / "editing_copilot" / "resolve.py"):
            text = f.read_text(encoding="utf-8")
            for banned in ("socket", "urllib", "requests", "subprocess", "eval(", "exec(", "os.system", "http.server"):
                self.assertNotIn(banned, text.replace("spec.loader.exec_module", ""), (f.name, banned))


if __name__ == "__main__":
    unittest.main()
