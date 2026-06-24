import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from src.orin.control.desktop_controller import (
    handle_open_app, handle_close_app, handle_focus_app, handle_list_apps
)
from src.orin.control.process_controller import KNOWN_APPS


class TestDesktopController(unittest.TestCase):
    def test_handle_open_app_missing_name(self):
        result = handle_open_app()
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "MISSING_ENTITY")

    @patch("src.orin.control.process_controller.os.system")
    def test_handle_open_app_known(self, mock_system):
        mock_system.return_value = 0
        result = handle_open_app(app_name="notepad")
        self.assertTrue(result.ok)

    @patch("src.orin.control.process_controller.os.system")
    def test_handle_open_app_chrome(self, mock_system):
        mock_system.return_value = 0
        result = handle_open_app(app_name="chrome")
        self.assertTrue(result.ok)

    def test_handle_close_app_missing_name(self):
        result = handle_close_app()
        self.assertFalse(result.ok)

    @patch("src.orin.control.process_controller.subprocess.run")
    def test_handle_close_app_known(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = handle_close_app(app_name="notepad")
        self.assertTrue(result.ok)

    def test_known_apps_dict(self):
        self.assertIn("chrome", KNOWN_APPS)
        self.assertIn("notepad", KNOWN_APPS)
        self.assertIn("vscode", KNOWN_APPS)
        self.assertIn("file explorer", KNOWN_APPS)

    @patch("src.orin.control.desktop_controller.list_running")
    def test_handle_list_apps(self, mock_list):
        mock_list.return_value.ok = True
        result = handle_list_apps()
        self.assertTrue(result.ok)

    @patch("src.orin.control.desktop_controller.win32gui")
    def test_handle_focus_app_found(self, mock_win32):
        mock_win32.IsWindowVisible.return_value = True
        mock_win32.GetWindowText.return_value = "Google Chrome"
        mock_win32.EnumWindows.side_effect = lambda proc, windows: windows.append(1)

        result = handle_focus_app(app_name="chrome")
        self.assertTrue(result.ok)

    @patch("src.orin.control.desktop_controller.win32gui")
    def test_handle_focus_app_not_found(self, mock_win32):
        mock_win32.IsWindowVisible.return_value = True
        mock_win32.GetWindowText.return_value = "Some Other Window"
        mock_win32.EnumWindows.side_effect = lambda proc, windows: None

        result = handle_focus_app(app_name="nonexistent")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
