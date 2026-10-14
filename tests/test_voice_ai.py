import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from editing_copilot import assistant, config, live, nlu, voice
from editing_copilot.commands import parse_command


def cfg(**over):
    c, _ = config.load_config(Path(tempfile.mkdtemp()))
    for k, v in over.items():
        c[k] = v
    return c


class NluTests(unittest.TestCase):
    def test_spoken_numbers(self):
        self.assertEqual(nlu.words_to_numbers("frame two hundred and five"), "frame 205")
        self.assertEqual(nlu.words_to_numbers("frame twenty five"), "frame 25")
        self.assertEqual(nlu.words_to_numbers("add a marker"), "add a marker")

    def test_commands_map_to_grammar(self):
        cases = {
            "add a marker at twenty five seconds called Intro colour red": "add marker at frame 625 named Intro color Red",
            "put a guide at frame ten named Review": "add guide at frame 10 named Review",
            "cut the selected clip at frame 30": "split clip selected at frame 30",
            "shorten the selected clip by five": "trim clip selected end by 5 frames",
            "add guide at 00:00:02:05 named X": "add guide at frame 55 named X",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                intent = nlu.interpret(spoken, 25)
                self.assertEqual((intent.kind, intent.value), ("command", expected))
                parse_command(intent.value)

    def test_controls_and_live(self):
        self.assertEqual(nlu.interpret("Apply.").value, "apply")
        self.assertEqual(nlu.interpret("stop").kind, "control")
        self.assertEqual(nlu.interpret("play").value, "play")
        self.assertEqual(nlu.interpret("marker here", editor="kdenlive").value, "guide")
        self.assertEqual(nlu.interpret("add marker here", editor="resolve").value, "marker")
        self.assertEqual(nlu.interpret("make it cinematic").kind, "unknown")

    def test_wake_word(self):
        self.assertEqual(nlu.strip_wake_word("Hey Copilot, play", "copilot", True), "play")
        self.assertIsNone(nlu.strip_wake_word("play", "copilot", True))
        self.assertEqual(nlu.strip_wake_word("play", "copilot", False), "play")


class ConfigTests(unittest.TestCase):
    def test_invalid_values_fall_back(self):
        d = Path(tempfile.mkdtemp())
        (d / "config.json").write_text(json.dumps({"mode": "paid", "voice": {"sample_rate": "x"}, "junk": 1}))
        c, warnings = config.load_config(d)
        self.assertEqual(c["mode"], "auto")
        self.assertEqual(c["voice"]["sample_rate"], 16000)
        self.assertEqual(len(warnings), 2)

    def test_corrupt_file(self):
        d = Path(tempfile.mkdtemp()); (d / "config.json").write_text("{nope")
        c, warnings = config.load_config(d)
        self.assertEqual(c["mode"], "auto"); self.assertTrue(warnings)

    def test_roundtrip_and_custom_shortcut(self):
        d = Path(tempfile.mkdtemp())
        c, _ = config.load_config(d); c["mode"] = "local"
        c["live_control"]["kdenlive_shortcuts"]["Ripple Delete"] = "shift+delete"
        config.save_config(d, c)
        c2, w = config.load_config(d)
        self.assertEqual(c2["mode"], "local"); self.assertEqual(w, [])
        self.assertEqual(c2["live_control"]["kdenlive_shortcuts"]["ripple delete"], "shift+delete")


class AssistantTests(unittest.TestCase):
    def test_rules_need_no_backend(self):
        c = cfg(mode="online")
        with patch.object(assistant, "_post", side_effect=AssertionError("no network")):
            self.assertEqual(assistant.understand("play", c).value, "play")

    def test_chain_by_mode(self):
        c = cfg(); c["local"]["llm"] = "ollama"
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual([n for n, _ in assistant.llm_chain(c)], ["ollama"])
        with patch.dict("os.environ", {"GROQ_API_KEY": "k"}):
            self.assertEqual([n for n, _ in assistant.llm_chain(c)], ["groq", "ollama"])
            c["mode"] = "local"; self.assertEqual([n for n, _ in assistant.llm_chain(c)], ["ollama"])

    def test_llm_output_validated(self):
        c = cfg(mode="online")
        reply = {"choices": [{"message": {"content": "add marker at frame 50 named \"Hook\" color Blue"}}]}
        with patch.dict("os.environ", {"GROQ_API_KEY": "k"}), patch.object(assistant, "_post", return_value=reply):
            i = assistant.understand("mark the hook two seconds in please, in blue", c)
        self.assertEqual(i.kind, "command"); parse_command(i.value)
        bad = {"choices": [{"message": {"content": "rm -rf / ; delete everything"}}]}
        with patch.dict("os.environ", {"GROQ_API_KEY": "k"}), patch.object(assistant, "_post", return_value=bad):
            self.assertEqual(assistant.understand("do something weird", c).kind, "unknown")

    def test_online_failure_falls_back_to_local(self):
        c = cfg(mode="auto"); c["local"]["llm"] = "ollama"
        calls = []
        def post(url, *a, **k):
            calls.append(url)
            if "groq" in url:
                raise assistant.AssistantError("down")
            return {"message": {"content": "undo"}}
        with patch.dict("os.environ", {"GROQ_API_KEY": "k"}), patch.object(assistant, "_post", side_effect=post):
            self.assertEqual(assistant.understand("revert whatever you just did", c).value, "undo")
        self.assertEqual(len(calls), 2)

    def test_gemini_payload(self):
        c = cfg(mode="online"); c["online"]["provider"] = "gemini"
        seen = {}
        def post(url, payload, headers, timeout):
            seen.update(url=url, headers=headers)
            return {"candidates": [{"content": {"parts": [{"text": "inspect"}]}}]}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "g"}), patch.object(assistant, "_post", side_effect=post):
            self.assertEqual(assistant.understand("tell me what is on the timeline", c).value, "inspect")
        self.assertIn("generateContent", seen["url"]); self.assertEqual(seen["headers"]["x-goog-api-key"], "g")


class VoiceTests(unittest.TestCase):
    def test_build_recognizer_modes(self):
        d = Path(tempfile.mkdtemp())
        c = cfg(mode="online")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(voice.VoiceError):
                voice.build_recognizer(c, d)
        with patch.dict("os.environ", {"GROQ_API_KEY": "k"}):
            self.assertIsInstance(voice.build_recognizer(c, d), voice.GroqRecognizer)
        c["mode"] = "local"
        with self.assertRaises(voice.VoiceError):  # no model installed in temp dir
            voice.build_recognizer(c, d)

    def test_fallback_recognizer(self):
        class Bad:
            name = "bad"
            def transcribe(self, pcm): raise voice.VoiceError("offline")
        class Good:
            name = "good"
            def transcribe(self, pcm): return "play"
        r = voice.FallbackRecognizer(Bad(), Good)
        self.assertEqual(r.transcribe(b"\0\0"), "play"); self.assertEqual(r.name, "good")

    def test_listener_endpointing(self):
        import array, math, threading
        rate = 16000
        loud = array.array("h", (int(8000 * math.sin(i / 5)) for i in range(rate // 10))).tobytes()
        quiet = bytes(rate // 10 * 2)
        chunks = [quiet] * 3 + [loud] * 6 + [quiet] * 10 + [b""]
        class Stream:
            def read(self, n): return (chunks.pop(0) if chunks else b"", False)
            def stop(self): pass
            def close(self): pass
        got, done = [], threading.Event()
        class Rec:
            name = "fake"
            def transcribe(self, pcm): got.append(len(pcm)); return "copilot play"
        l = voice.VoiceListener(Rec(), lambda t: (got.append(t), done.set()), print, stream_factory=Stream).start()
        self.assertTrue(done.wait(5)); l.stop()
        self.assertIn("copilot play", got)

    def test_wav(self):
        self.assertTrue(voice.pcm_to_wav(b"\0\0" * 10, 16000).startswith(b"RIFF"))


class LiveTests(unittest.TestCase):
    def test_shortcuts_parse(self):
        c = cfg()
        for table in ("kdenlive_shortcuts", "resolve_shortcuts"):
            for action, spec in c["live_control"][table].items():
                with self.subTest(action=action):
                    live.parse_shortcut(spec)
        self.assertEqual(live.parse_shortcut("shift+r"), [0x10, ord("R")])
        with self.assertRaises(live.LiveControlError):
            live.parse_shortcut("hyper+q")

    def test_unknown_action_and_disabled(self):
        c = cfg()
        with self.assertRaises(live.LiveControlError):
            live.send_action("kdenlive", "marker", c)  # kdenlive uses guides
        c["live_control"]["enabled"] = False
        with self.assertRaises(live.LiveControlError):
            live.send_action("kdenlive", "play", c)


if __name__ == "__main__":
    unittest.main()


class RealVoskTest(unittest.TestCase):
    """Runs only when a model and a 16 kHz s16le sample are provided via env vars."""

    def test_real_audio(self):
        import os
        model, sample = os.environ.get("EC_VOSK_MODEL"), os.environ.get("EC_VOSK_SAMPLE")
        if not (model and sample):
            self.skipTest("EC_VOSK_MODEL / EC_VOSK_SAMPLE not set")
        text = voice.VoskRecognizer(Path(model), 16000).transcribe(Path(sample).read_bytes())
        intent = nlu.interpret(nlu.strip_wake_word(text, "copilot", False))
        self.assertEqual(intent.value, "add guide at frame 25 named intro" if "guide" in text else "add marker at frame 25 named intro", text)
