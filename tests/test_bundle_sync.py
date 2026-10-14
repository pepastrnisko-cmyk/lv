"""Bundled Resolve integration copies must stay identical to their sources."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ((ROOT / "src" / "editing_copilot" / "resolve.py", ROOT / "resources" / "integration" / "editing_copilot" / "resolve.py"),
         (ROOT / "integrations" / "resolve" / "Editing Copilot.py", ROOT / "resources" / "integration" / "Editing Copilot.py"))


def _text(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


class BundleSyncTests(unittest.TestCase):
    def test_copies_match(self):
        for source, copy in PAIRS:
            with self.subTest(copy=copy.name):
                self.assertEqual(_text(source), _text(copy), f"{copy} drifted from {source}")


if __name__ == "__main__":
    unittest.main()