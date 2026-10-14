"""Desktop shortcut COM regressions; fixtures never touch user install folders."""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from editing_copilot.install import install_companion


class InstallComTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source.exe"
        self.source.write_bytes(b"QA installer fixture")
        self.com = types.ModuleType("pythoncom")
        self.com.COINIT_APARTMENTTHREADED = 2
        self.com.CoInitializeEx = Mock()
        self.com.CoUninitialize = Mock()
        self.client = types.ModuleType("win32com.client")
        self.client.Dispatch = Mock()
        self.package = types.ModuleType("win32com")
        self.package.__path__ = []
        self.package.client = self.client

    def install(self):
        with patch.dict(sys.modules, {"pythoncom": self.com, "win32com": self.package,
                                      "win32com.client": self.client}), \
                patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "executable", str(self.source)), \
                patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            return install_companion(self.base / "resources", self.base / "local")

    def assert_executable_installed(self, result):
        destination = Path(result["executable"])
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())
        self.assertTrue(destination.is_relative_to(self.base))

    def test_shortcut_initializes_com_before_dispatch_and_balances_success(self):
        shell = Mock()
        def dispatch(name):
            self.com.CoInitializeEx.assert_called_once_with(2)
            self.com.CoUninitialize.assert_not_called()
            self.assertEqual(name, "WScript.Shell")
            return shell
        self.client.Dispatch.side_effect = dispatch
        result = self.install()
        self.assert_executable_installed(result)
        self.assertTrue(result["shortcut"].endswith("Editing Copilot.lnk"))
        self.assertTrue(Path(result["shortcut"]).is_relative_to(self.base))
        item = shell.CreateShortcut.return_value
        self.assertEqual(item.TargetPath, result["executable"])
        item.Save.assert_called_once()
        self.com.CoUninitialize.assert_called_once()

    def test_shortcut_failure_balances_com_and_retains_valid_installation(self):
        self.client.Dispatch.side_effect = RuntimeError("shortcut unavailable")
        result = self.install()
        self.assert_executable_installed(result)
        self.assertIsNone(result["shortcut"])
        self.com.CoInitializeEx.assert_called_once_with(2)
        self.com.CoUninitialize.assert_called_once()

    def test_shortcut_save_failure_balances_com(self):
        self.client.Dispatch.return_value.CreateShortcut.return_value.Save.side_effect = RuntimeError("save unavailable")
        result = self.install()
        self.assert_executable_installed(result)
        self.assertIsNone(result["shortcut"])
        self.com.CoUninitialize.assert_called_once()

    def test_failed_com_initialization_does_not_uninitialize_another_apartment(self):
        self.com.CoInitializeEx.side_effect = RuntimeError("different COM apartment")
        result = self.install()
        self.assert_executable_installed(result)
        self.assertIsNone(result["shortcut"])
        self.client.Dispatch.assert_not_called()
        self.com.CoUninitialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
