import unittest

from editing_copilot.commands import Command, MAX_FRAME, UnsupportedCommand, parse_command


class CommandTests(unittest.TestCase):
    def test_read_commands(self):
        for text, operation in (("inspect", "inspect"), ("INSPECT PROJECT", "inspect"), ("inspect timeline", "inspect"), ("describe project", "inspect"), ("list clips", "list_clips"), ("list timeline clips", "list_clips"), ("export report", "export_report"), ("undo", "undo"), (" STOP ", "stop")):
            with self.subTest(text=text):
                self.assertEqual(parse_command(text), Command(operation, {}))

    def test_marker_name_case_and_unicode(self):
        command = parse_command("ADD MARKER at FRAME 12 named Cam A – Überfahrt color BLUE")
        self.assertEqual(command.operation, "add_marker")
        self.assertEqual(command.args, {"frame": 12, "name": "Cam A – Überfahrt", "color": "Blue"})

    def test_marker_default_color(self):
        self.assertEqual(parse_command("add marker at frame 0 named Opening").args, {"frame": 0, "name": "Opening", "color": "Green"})

    def test_quoted_name_contains_color_suffix(self):
        self.assertEqual(parse_command('add marker at frame 9 named "Opening color Green" color RED').args, {"frame": 9, "name": "Opening color Green", "color": "Red"})

    def test_quoted_json_escapes(self):
        self.assertEqual(parse_command('add marker at frame 9 named "Say \\"Hello\\""').args["name"], 'Say "Hello"')

    def test_guide(self):
        self.assertEqual(parse_command('add guide at frame 24 named "Act Two"').args, {"frame": 24, "name": "Act Two"})

    def test_guide_name_color_is_text(self):
        self.assertEqual(parse_command("add guide at frame 24 named Color Green").args["name"], "Color Green")

    def test_split_preserves_id(self):
        result = parse_command("split clip Sequence-A|Video_1|2 at frame 25")
        self.assertEqual(result, Command("split_clip", {"clip_id": "Sequence-A|Video_1|2", "frame": 25}, True))

    def test_uuid_sequence_id(self):
        identifier = "{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}|video_lane|0"
        self.assertEqual(parse_command(f"split clip {identifier} at frame 25").args["clip_id"], identifier)

    def test_trim_is_negative_no_ripple(self):
        result = parse_command("trim clip A:2 end by 7 frames")
        self.assertEqual(result, Command("trim_clip", {"clip_id": "A:2", "edge": "end", "delta_frames": -7, "ripple": False}, True))

    def test_one_frame_trim(self):
        self.assertEqual(parse_command("trim clip 42 end by 1 frame").args["delta_frames"], -1)

    def test_frame_limits(self):
        self.assertEqual(parse_command(f"split clip x at frame {MAX_FRAME}").args["frame"], MAX_FRAME)
        for value in ("-1", str(MAX_FRAME + 1), "0" * 1000, "3.5", "NaN", "1e4"):
            with self.subTest(value=value):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(f"split clip x at frame {value}")

    def test_trim_limits(self):
        for value in ("0", "-1", str(MAX_FRAME + 1)):
            with self.subTest(value=value):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(f"trim clip x end by {value} frames")

    def test_subjective_grading_fails_explicitly(self):
        for text in ("make it dramatic", "match clip 1 color to clip 2", "add cinematic look", "increase exposure", "brighter reds"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(UnsupportedCommand, "not implemented"):
                    parse_command(text)

    def test_negation_and_ambiguity_rejected(self):
        for text in ("do not split clip 1 at frame 20", "don't trim clip A end by 5 frames", "maybe split clip 1 at frame 20", "split this at frame 20", "trim clip 1 a little", "split clip 1 at frame 20 and move it", "split clip 1 at frame 20 then stop"):
            with self.subTest(text=text):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(text)

    def test_negation_in_label_is_valid(self):
        self.assertEqual(parse_command('add marker at frame 1 named "Do Not Cut"').args["name"], "Do Not Cut")

    def test_invalid_names(self):
        for text in ('add marker at frame 1 named ""', 'add guide at frame 1 named "   "', 'add guide at frame 1 named "bad\\nname"', 'add marker at frame 1 named "unterminated', 'add marker at frame 1 named "abc" trailing', "add marker at frame 1 named " + "x" * 257):
            with self.subTest(text=text):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(text)

    def test_invalid_color(self):
        with self.assertRaisesRegex(UnsupportedCommand, "color"):
            parse_command("add marker at frame 1 named Opening color Orange")

    def test_no_multiline_commands(self):
        for text in ("inspect\nstop", "inspect\x00", "list\tclips"):
            with self.subTest(text=text):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(text)

    def test_no_code_or_paths_as_command_targets(self):
        for text in ('eval("inspect")', "split clip C:/video.mp4 at frame 1", "split clip $(whoami) at frame 1", "stop; start", "python script.py", "__import__('os').system('calc')"):
            with self.subTest(text=text):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(text)

    def test_literal_name_does_not_execute(self):
        name = "$(whoami); __import__('os')"
        self.assertEqual(parse_command(f'add marker at frame 1 named "{name}"').args["name"], name)

    def test_non_text_and_empty_rejected(self):
        for text in (None, 123, {}, "", " ", "x" * 2049):
            with self.subTest(text=text):
                with self.assertRaises(UnsupportedCommand):
                    parse_command(text)


if __name__ == "__main__":
    unittest.main()
