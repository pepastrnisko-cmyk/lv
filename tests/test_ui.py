from pathlib import Path
import shutil
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import json

from editing_copilot.runtime import Controller
from editing_copilot.ui import CopilotApp, timeline_rows, save_report_atomic, validate_report_destination, initial_window_size
from editing_copilot.history import CancellationSupervisor


RESOURCES = Path(__file__).resolve().parents[1] / "resources"


class TimelineRowsTests(unittest.TestCase):
    def test_window_fits_small_and_dpi_virtualized_screens(self):
        for screen, expected in (((1536, 864), (1180, 754)), ((1280, 720), (1180, 610)), ((1920, 1080), (1180, 850))):
            with self.subTest(screen=screen):
                width, height = initial_window_size(*screen)
                self.assertEqual((width, height), expected)
                self.assertLess(width, screen[0])
                self.assertLess(height, screen[1])

    def test_kdenlive_nested_identity_preserved(self):
        snapshot = {"editor": "kdenlive", "sequences": [{"name": "Sequence A", "tracks": [{"name": "V1", "locked": True, "playlists": [{"instances": [{"instance_id": "uuid|lane|0", "name": "Shot"}]}]}]}]}
        self.assertEqual(timeline_rows(snapshot), [{"instance_id": "uuid|lane|0", "name": "Shot", "sequence_name": "Sequence A", "track_name": "V1", "track_locked": True}])

    def test_resolve_frames_remain_absolute(self):
        snapshot = {"editor": "resolve", "identity": {"timeline_name": "Cut"}, "clips": [{"id": "unique-7", "track_type": "video", "track": 2, "start_frame": 86400, "end_frame": 86500}]}
        row = timeline_rows(snapshot)[0]
        self.assertEqual(row["instance_id"], "unique-7")
        self.assertEqual(row["timeline_in"], 86400)
        self.assertEqual(row["timeline_out_exclusive"], 86500)


class DesktopSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.project = self.folder / "Project.kdenlive"
        shutil.copyfile(RESOURCES / "demo.kdenlive", self.project)
        self.controller = Controller(self.folder / "data")
        self.controller.select("kdenlive", self.project)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.controller.close()
            self.temp.cleanup()
            self.skipTest("Desktop display is unavailable.")
        self.root.withdraw()
        self.app = CopilotApp(self.root, self.controller, RESOURCES, load_demo=False, enable_hotkey=False)
        self.app._voice_checked = True

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.close()
            deadline = time.monotonic() + 3
            while self.app._active_thread is not None and self.app._active_thread.is_alive() and time.monotonic() < deadline:
                try:
                    self.root.update()
                except tk.TclError:
                    break
                time.sleep(.005)
            try:
                self.root.update()
                self.root.destroy()
            except tk.TclError:
                pass
        self.temp.cleanup()

    def wait_idle(self):
        deadline = time.monotonic() + 4
        while self.app._busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.005)
        self.root.update()
        self.assertFalse(self.app._busy, "Desktop worker did not return promptly")

    def test_small_window_keeps_footer_controls_visible(self):
        self.root.geometry("1000x720")
        self.root.deiconify()
        self.root.update()
        bottom = self.root.winfo_rooty() + self.root.winfo_height()
        for widget in (self.app.export_button, self.app.open_output_button, self.app.progress):
            with self.subTest(widget=str(widget)):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_height(), 1)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)

    def inspect(self):
        self.app.inspect_project()
        self.wait_idle()
        self.assertEqual(len(self.app._row_ids), 2)

    def test_window_inspects_real_project_and_previews_guide(self):
        self.inspect()
        self.app.command.set('add guide at frame 10 named "UI Smoke"')
        self.app.preview_command()
        self.wait_idle()
        self.assertIsNotNone(self.controller.preview)
        self.assertEqual(self.controller.preview["plan"]["operation"], "add_guide")
        self.assertEqual(str(self.app.apply_button["state"]), "normal")
        self.assertEqual(self.project.read_bytes(), (RESOURCES / "demo.kdenlive").read_bytes())

    def test_selected_clip_preview_apply_and_undo(self):
        self.inspect()
        row = next(iter(self.app._row_ids))
        self.app.clip_tree.selection_set(row)
        self.root.update()
        self.app.command.set("split clip selected at frame 25")
        self.app.preview_command()
        self.wait_idle()
        self.assertIsNotNone(self.controller.preview)
        self.assertEqual(str(self.app.apply_button["state"]), "normal")
        self.app.apply_preview()
        self.wait_idle()
        self.assertNotEqual(self.controller.path, self.project)
        self.assertTrue(self.controller.path.is_file())
        self.assertIn("reopen", self.app.result_title.get().casefold())
        self.assertIsNone(self.controller.preview)
        with patch("editing_copilot.ui.find_kdenlive_executable", return_value=Path("C:/Program Files/kdenlive/bin/kdenlive.exe")), patch("editing_copilot.ui.subprocess.Popen") as launch:
            self.app.open_output()
            self.assertEqual(launch.call_args.args[0][1], str(self.controller.path))
        self.app.undo()
        self.wait_idle()
        self.assertEqual(self.controller.path, self.project)
        self.assertEqual(self.app._last_output, self.project)
        with patch("editing_copilot.ui.find_kdenlive_executable", return_value=Path("C:/Program Files/kdenlive/bin/kdenlive.exe")), patch("editing_copilot.ui.subprocess.Popen") as launch:
            self.app.open_output()
            self.assertEqual(launch.call_args.args[0][1], str(self.project))

    def test_open_current_project_never_uses_previous_copy(self):
        other = self.folder / "Other.kdenlive"
        shutil.copyfile(self.project, other)
        self.app._last_output = self.project
        self.controller.select("kdenlive", other)
        with patch("editing_copilot.ui.find_kdenlive_executable", return_value=Path("C:/Program Files/kdenlive/bin/kdenlive.exe")), patch("editing_copilot.ui.subprocess.Popen") as launch:
            self.app.open_output()
            self.assertEqual(launch.call_args.args[0][1], str(other))
            self.controller.select("resolve")
            self.app._update_buttons()
            self.assertEqual(str(self.app.open_output_button["state"]), "disabled")
            self.app.open_output()
            self.assertEqual(launch.call_count, 1)

    def test_export_rejects_project_filename_before_writing(self):
        self.inspect()
        original = self.project.read_bytes()
        with patch("editing_copilot.ui.filedialog.asksaveasfilename", return_value=str(self.project)):
            self.app.export_report()
        self.assertFalse(self.app._busy)
        self.assertEqual(self.project.read_bytes(), original)
        self.assertIn(".json", self.app.result_text.get("1.0", "end"))

    def test_export_json_is_complete_and_no_temp_remains(self):
        self.inspect()
        report = self.folder / "inspection.json"
        report.write_text('{"old":true}', encoding="utf-8")
        with patch("editing_copilot.ui.filedialog.asksaveasfilename", return_value=str(report)):
            self.app.export_report()
        self.wait_idle()
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["inspection"]["editor"], "kdenlive")
        self.assertEqual(list(self.folder.glob(".copilot-report-*.tmp")), [])

    def test_escape_is_bound_to_stop(self):
        self.assertTrue(self.root.bind("<Escape>"))

    def test_changed_command_invalidates_preview(self):
        self.inspect()
        self.app.command.set('add guide at frame 10 named "Original"')
        self.app.preview_command()
        self.wait_idle()
        self.app.command.set('add guide at frame 11 named "Changed"')
        self.assertIsNone(self.controller.preview)
        self.assertEqual(str(self.app.apply_button["state"]), "disabled")

    def test_changed_clip_selection_invalidates_preview(self):
        self.inspect()
        row = next(iter(self.app._row_ids))
        self.app.clip_tree.selection_set(row)
        self.root.update()
        self.app.command.set("split clip selected at frame 25")
        self.app.preview_command()
        self.wait_idle()
        row = list(self.app._row_ids)[1]
        self.app.clip_tree.selection_set(row)
        self.root.update()
        self.assertIsNone(self.controller.preview)

    def test_stop_revokes_preview_immediately(self):
        self.inspect()
        self.app.command.set('add guide at frame 10 named "Do not apply"')
        self.app.preview_command()
        self.wait_idle()
        lease = self.controller.supervisor.capture()
        self.app.stop()
        self.assertFalse(lease.is_active())
        self.assertIsNone(self.controller.preview)
        self.assertEqual(str(self.app.apply_button["state"]), "disabled")

    def test_voice_result_only_fills_command(self):
        self.app._success("dictate", 'add guide at frame 10 named "Voice only"')
        self.assertEqual(self.app.command.get(), 'add guide at frame 10 named "Voice only"')
        self.assertIsNone(self.controller.preview)
        self.assertEqual(self.controller.history.list_recent(), [])

    def test_rejects_subjective_color_without_mutation(self):
        self.inspect()
        original = self.project.read_bytes()
        self.app.command.set("make this dramatic")
        self.app.preview_command()
        self.wait_idle()
        self.assertIn("not implemented", self.app.result_text.get("1.0", "end"))
        self.assertEqual(self.project.read_bytes(), original)
        self.assertIsNone(self.controller.preview)


class ReportSafetyTests(unittest.TestCase):
    def test_media_and_project_suffixes_rejected(self):
        for name in ("source.kdenlive", "video.mp4", "audio.wav", "timeline.drp", "without-extension"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_report_destination(Path(name))

    def test_source_asset_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            source.write_text("source data", encoding="utf-8")
            with self.assertRaises(ValueError):
                save_report_atomic(source, "{}", CancellationSupervisor().capture(), [source])
            self.assertEqual(source.read_text(encoding="utf-8"), "source data")

    def test_nonregular_destination_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "report.json"
            target.mkdir()
            with self.assertRaises(ValueError):
                validate_report_destination(target)

    def test_cancellation_keeps_existing_report(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "report.json"
            target.write_text("old", encoding="utf-8")
            supervisor = CancellationSupervisor()
            lease = supervisor.capture()
            supervisor.stop()
            with self.assertRaises(RuntimeError):
                save_report_atomic(target, "new", lease)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")


if __name__ == "__main__":
    unittest.main()
