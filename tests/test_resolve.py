"""Resolve contract tests use fake editor objects and never mutate a user project."""
import copy
import builtins
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from editing_copilot.resolve import OWNER_PREFIX, ResolveAdapter, ResolveError, connect_external


class Clip:
    def GetUniqueId(self): return "clip-1"
    def GetName(self): return "shot.mov"
    def GetStart(self): return 86400
    def GetEnd(self): return 86500
    def GetDuration(self): return 100
    def GetProperties(self): return {"ZoomX": 1.0, "ZoomY": 1.0}


class Timeline:
    def __init__(self):
        self.markers = {}
        self.uid = "timeline-1"
        self.start = 86400
        self.end = 86600
        self.add_calls = 0
        self.delete_calls = 0
        self.reject_add = False
        self.reject_delete = False
        self.alter_add = False
        self.after_add = None
    def GetUniqueId(self): return self.uid
    def GetName(self): return "Main timeline"
    def GetStartFrame(self): return self.start
    def GetEndFrame(self): return self.end
    def GetSettings(self): return {"timelineFrameRate": "25", "timelineResolutionWidth": "1920"}
    def GetTrackCount(self, kind): return 1 if kind == "video" else 0
    def GetItemListInTrack(self, kind, index): return [Clip()]
    def GetMarkers(self): return copy.deepcopy(self.markers)
    def AddMarker(self, frame, color, name, note, duration, customData):
        self.add_calls += 1
        if self.reject_add: return False
        self.markers[float(frame)] = {"color": color, "name": name, "note": note,
                                      "duration": float(duration), "customData": customData}
        if self.alter_add: self.markers[float(frame)]["name"] += " changed"
        if self.after_add: self.after_add()
        return True
    def DeleteMarkerAtFrame(self, frame):
        self.delete_calls += 1
        if self.reject_delete: return False
        return self.markers.pop(float(frame), None) is not None


class Project:
    def __init__(self):
        self.timeline = Timeline()
        self.uid = "project-1"
        self.rendering = False
    def GetUniqueId(self): return self.uid
    def GetName(self): return "Fixture project"
    def GetCurrentTimeline(self): return self.timeline
    def IsRenderingInProgress(self): return self.rendering


class Manager:
    def __init__(self): self.project = Project()
    def GetCurrentProject(self): return self.project


class Resolve:
    def __init__(self): self.manager = Manager()
    def GetProjectManager(self): return self.manager
    def GetVersionString(self): return "21.1.1.10"
    def GetProductName(self): return "DaVinci Resolve Studio"


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.resolve = Resolve()
        self.adapter = ResolveAdapter(self.resolve)
        self.project = self.resolve.manager.project
        self.timeline = self.project.timeline
    def plan(self, **kwargs):
        args = {"frame": 10, "name": "Review this"}
        args.update(kwargs)
        return self.adapter.plan("add_marker", args)
    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(ResolveError) as caught: function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_describe_is_json_serializable_and_read_only(self):
        result = self.adapter.describe()
        self.assertEqual(result["identity"]["start_frame"], 86400)
        self.assertEqual(result["edition"], "Studio")
        self.assertEqual(result["clips"][0]["name"], "shot.mov")
        json.dumps(result, allow_nan=False)
        self.assertEqual(self.timeline.add_calls, 0)
        self.assertEqual(self.timeline.delete_calls, 0)

    def test_connect_callable_is_supported(self):
        self.assertEqual(ResolveAdapter(lambda: self.resolve).describe()["version"], "21.1.1.10")

    def test_blackmagic_module_self_replacement_is_honored(self):
        shim = SimpleNamespace()
        native = SimpleNamespace(scriptapp=lambda name: self.resolve if name == "Resolve" else None)
        def execute(module):
            self.assertIs(sys.modules["DaVinciResolveScript"], shim)
            sys.modules["DaVinciResolveScript"] = native
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=execute))
        original_import = builtins.__import__
        def importing(name, *args, **kwargs):
            if name == "DaVinciResolveScript": raise ImportError("module not on search path")
            return original_import(name, *args, **kwargs)
        with patch.dict(sys.modules), patch.object(builtins, "__import__", importing), \
                patch("editing_copilot.resolve.Path.is_file", return_value=True), \
                patch("editing_copilot.resolve.importlib.util.spec_from_file_location", return_value=spec), \
                patch("editing_copilot.resolve.importlib.util.module_from_spec", return_value=shim):
            sys.modules.pop("DaVinciResolveScript", None)
            self.assertIs(connect_external(), self.resolve)
            self.assertIs(sys.modules["DaVinciResolveScript"], native)

    def test_no_project(self):
        self.resolve.manager.project = None
        self.assert_code("no_project", self.adapter.describe)

    def test_no_timeline(self):
        self.project.timeline = None
        self.assert_code("no_timeline", self.adapter.describe)

    def test_inspect_plan_never_mutates(self):
        result = self.adapter.apply(self.adapter.plan("inspect"))
        self.assertEqual(result["editor"], "resolve")
        self.assertEqual(self.timeline.add_calls, 0)

    def test_unsupported_operation(self):
        self.assert_code("unsupported_operation", self.adapter.plan, "color_match", {})

    def test_offset_frame_is_not_absolute_timecode_frame(self):
        plan = self.plan(frame=0)
        self.adapter.apply(plan)
        self.assertIn(0, self.timeline.markers)
        self.assertNotIn(86400, self.timeline.markers)

    def test_reject_fraction_bool_and_string_frames(self):
        for frame in (2.5, True, "10"):
            self.assert_code("invalid_argument", self.plan, frame=frame)

    def test_range_validation(self):
        for args in ({"frame": -1}, {"frame": 200}, {"frame": 190, "duration": 11}, {"duration": 0}):
            self.assert_code("out_of_range", self.plan, **args)

    def test_reject_invalid_text_and_color(self):
        for args in ({"name": ""}, {"name": "a" * 257}, {"note": "x\x00y"}, {"color": "Orange"}):
            self.assert_code("invalid_argument", self.plan, **args)

    def test_unknown_argument_not_silently_ignored(self):
        self.assert_code("invalid_argument", self.plan, zoom=2)

    def test_stable_ids_required_for_mutation(self):
        self.timeline.uid = None
        self.assert_code("identity_unavailable", self.plan)

    def test_busy_editor_blocks_mutation(self):
        self.project.rendering = True
        self.assert_code("editor_busy", self.plan)

    def test_unknown_busy_state_blocks_mutation(self):
        self.project.rendering = None
        self.assert_code("editor_busy", self.plan)

    def test_add_and_verified_undo(self):
        transaction = self.adapter.apply(self.plan())
        self.assertTrue(transaction["marker"]["customData"].startswith(OWNER_PREFIX))
        self.assertEqual(self.timeline.markers[10]["name"], "Review this")
        result = self.adapter.undo(transaction)
        self.assertEqual(result["status"], "undone")
        self.assertEqual(self.timeline.markers, {})

    def test_apply_is_idempotent(self):
        plan = self.plan()
        first = self.adapter.apply(plan)
        second = self.adapter.apply(plan)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(self.timeline.add_calls, 1)

    def test_undo_is_idempotent(self):
        transaction = self.adapter.apply(self.plan())
        self.adapter.undo(transaction)
        self.assertTrue(self.adapter.undo(transaction)["idempotent"])
        self.assertEqual(self.timeline.delete_calls, 1)

    def test_existing_marker_preserved(self):
        self.timeline.markers[10] = {"name": "User marker", "customData": ""}
        self.assert_code("marker_conflict", self.plan)
        self.assertEqual(self.timeline.markers[10]["name"], "User marker")

    def test_changed_project_blocks_stale_plan(self):
        plan = self.plan()
        self.project.uid = "other-project"
        self.assert_code("stale_plan", self.adapter.apply, plan)
        self.assertEqual(self.timeline.add_calls, 0)

    def test_changed_timeline_blocks_stale_plan(self):
        plan = self.plan()
        self.timeline.uid = "other-timeline"
        self.assert_code("stale_plan", self.adapter.apply, plan)
        self.assertEqual(self.timeline.add_calls, 0)

    def test_changed_timeline_bounds_block_stale_plan(self):
        plan = self.plan()
        self.timeline.end += 1
        self.assert_code("stale_plan", self.adapter.apply, plan)

    def test_user_marker_added_after_preview_blocks_apply(self):
        plan = self.plan()
        self.timeline.markers[20] = {"name": "New user marker"}
        self.assert_code("stale_plan", self.adapter.apply, plan)
        self.assertEqual(self.timeline.add_calls, 0)

    def test_failed_add_is_not_reported_success(self):
        plan = self.plan()
        self.timeline.reject_add = True
        self.assert_code("verification_failed", self.adapter.apply, plan)

    def test_altered_readback_is_not_reported_success(self):
        plan = self.plan()
        self.timeline.alter_add = True
        self.assert_code("verification_failed", self.adapter.apply, plan)
        self.assertEqual(self.timeline.delete_calls, 0)

    def test_changed_marker_not_removed_by_undo(self):
        transaction = self.adapter.apply(self.plan())
        self.timeline.markers[10]["note"] = "User changed this"
        self.assert_code("undo_conflict", self.adapter.undo, transaction)
        self.assertEqual(self.timeline.delete_calls, 0)

    def test_moved_marker_not_removed_by_undo(self):
        transaction = self.adapter.apply(self.plan())
        self.timeline.markers[20] = self.timeline.markers.pop(10)
        self.assert_code("undo_conflict", self.adapter.undo, transaction)
        self.assertEqual(self.timeline.delete_calls, 0)

    def test_duplicate_ownership_blocks_undo(self):
        transaction = self.adapter.apply(self.plan())
        self.timeline.markers[20] = copy.deepcopy(self.timeline.markers[10])
        self.assert_code("undo_conflict", self.adapter.undo, transaction)

    def test_failed_delete_is_not_reported_success(self):
        transaction = self.adapter.apply(self.plan())
        self.timeline.reject_delete = True
        self.assert_code("verification_failed", self.adapter.undo, transaction)

    def test_foreign_transaction_rejected(self):
        transaction = self.adapter.apply(self.plan())
        transaction["marker"]["customData"] = "user-owned"
        self.assert_code("invalid_plan", self.adapter.undo, transaction)
        self.assertEqual(self.timeline.delete_calls, 0)

    def test_cancellation_before_apply(self):
        plan = self.plan()
        cancel = threading.Event()
        cancel.set()
        self.assert_code("cancelled", self.adapter.apply, plan, cancel)
        self.assertEqual(self.timeline.add_calls, 0)

    def test_cancellation_after_add_preserves_verified_marker(self):
        plan = self.plan()
        cancel = threading.Event()
        self.timeline.after_add = cancel.set
        transaction = self.adapter.apply(plan, cancel)
        self.assertEqual(transaction["status"], "applied")
        self.assertTrue(transaction["stopped_after_apply"])
        self.assertIn(10, self.timeline.markers)
        self.assertEqual(self.timeline.delete_calls, 0)

    def test_cancellation_before_undo_preserves_marker(self):
        transaction = self.adapter.apply(self.plan())
        self.assert_code("cancelled", self.adapter.undo, transaction, lambda: True)
        self.assertIn(10, self.timeline.markers)

    def test_tampered_negative_frame_rejected(self):
        plan = self.plan()
        plan["frame"] = -1
        self.assert_code("out_of_range", self.adapter.apply, plan)

    def test_invalid_marker_readback_blocks_plan(self):
        self.timeline.GetMarkers = lambda: None
        self.assert_code("readback_failed", self.plan)

    def test_non_integral_marker_position_blocks_plan(self):
        self.timeline.markers[1.5] = {"name": "Bad marker"}
        self.assert_code("readback_failed", self.plan)

    def test_native_menu_history_roundtrip_and_invalid_rejection(self):
        script = Path(__file__).resolve().parents[1] / "integrations/resolve/Editing Copilot.py"
        spec = importlib.util.spec_from_file_location("editing_copilot_menu_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            self.assertEqual(module._read_history(path), [])
            transaction = self.adapter.apply(self.plan())
            module._write_history(path, [transaction])
            self.assertEqual(module._read_history(path), [transaction])
            path.write_text("{\"schema\": 2, \"transactions\": []}", encoding="utf-8")
            with self.assertRaises(RuntimeError): module._read_history(path)

    def test_native_menu_has_no_arbitrary_execution_or_network_server(self):
        source = (Path(__file__).resolve().parents[1] / "integrations/resolve/Editing Copilot.py").read_text(encoding="utf-8")
        for token in ("eval(", "exec(", "subprocess", "socket", "http.server"):
            self.assertNotIn(token, source)

    def test_native_menu_ui_smoke_preview_apply_undo(self):
        script = Path(__file__).resolve().parents[1] / "integrations/resolve/Editing Copilot.py"
        spec = importlib.util.spec_from_file_location("editing_copilot_menu_ui_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        test = self

        class Widget:
            def __init__(self, props, children=None):
                self.props = props
                self.children = children or []
                self.Text = props.get("Text", "")
                self.PlainText = props.get("PlainText", "")
                self.Enabled = props.get("Enabled", True)

        class Events(dict):
            def __missing__(self, key):
                value = SimpleNamespace()
                self[key] = value
                return value

        class Window:
            def __init__(self, content):
                self.items = {}
                self.On = Events()
                def collect(widget):
                    if widget.props.get("ID"): self.items[widget.props["ID"]] = widget
                    for child in widget.children: collect(child)
                collect(content)
            def GetItems(self): return self.items
            def Show(self): pass
            def Hide(self): pass

        class UI:
            def FindWindow(self, window_id): return None
            def VGroup(self, props, children): return Widget(props, children)
            HGroup = VGroup
            def Label(self, props): return Widget(props)
            LineEdit = Label
            Button = Label
            TextEdit = Label

        class Dispatcher:
            def AddWindow(self, props, content):
                self.window = Window(content)
                return self.window
            def ExitLoop(self): pass
            def RunLoop(self):
                window = self.window
                test.assertIn("Fixture project", window.items["Output"].PlainText)
                window.items["Frame"].Text = "10"
                window.On["Preview"].Clicked(None)
                test.assertTrue(window.items["Apply"].Enabled)
                test.assertIn("READY TO APPLY", window.items["Output"].PlainText)
                window.On["Apply"].Clicked(None)
                test.assertIn("VERIFIED", window.items["Output"].PlainText)
                test.assertIn(10, test.timeline.markers)
                window.On["Undo"].Clicked(None)
                test.assertIn("VERIFIED UNDO", window.items["Output"].PlainText)
                test.assertEqual(test.timeline.markers, {})

        ui = UI()
        context = {"resolve": self.resolve, "fusion": SimpleNamespace(UIManager=ui),
                   "bmd": SimpleNamespace(UIDispatcher=lambda native_ui: Dispatcher())}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            with patch.object(module, "_history_path", return_value=path):
                module.main(context)
            saved = module._read_history(path)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["status"], "undone")

    def test_native_menu_without_uimanager_is_read_only(self):
        script = Path(__file__).resolve().parents[1] / "integrations/resolve/Editing Copilot.py"
        spec = importlib.util.spec_from_file_location("editing_copilot_menu_unavailable_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        context = {"resolve": self.resolve, "fusion": SimpleNamespace(UIManager=None), "bmd": None}
        stream = io.StringIO()
        with redirect_stdout(stream): module.main(context)
        self.assertIn("does not expose UIManager", stream.getvalue())
        self.assertEqual(self.timeline.add_calls, 0)

    def test_native_menu_finds_fixed_per_user_integration_package(self):
        script = Path(__file__).resolve().parents[1] / "integrations/resolve/Editing Copilot.py"
        spec = importlib.util.spec_from_file_location("editing_copilot_menu_package_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            utility = base / "Resolve/Scripts/Utility"
            utility.mkdir(parents=True)
            package_root = base / "Local/EditingCopilot/integration"
            package = package_root / "editing_copilot"
            package.mkdir(parents=True)
            (package / "resolve.py").write_text("# fixture", encoding="utf-8")
            old_path = list(sys.path)
            try:
                with patch.object(module, "__file__", str(utility / "Editing Copilot.py")), \
                        patch.dict(os.environ, {"LOCALAPPDATA": str(base / "Local")}):
                    module._package_path()
                    self.assertEqual(sys.path[0], str(package_root))
            finally:
                sys.path[:] = old_path


if __name__ == "__main__":
    unittest.main()
