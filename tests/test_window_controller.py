import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from engine.control.window_controller import (
    handle_get_active_window, handle_list_windows, handle_focus_window,
    handle_minimize_window, handle_maximize_window
)


class TestWindowController(unittest.TestCase):
    @patch("engine.control.window_controller.win32gui")
    def test_get_active_window(self, mock_win32):
        mock_win32.GetForegroundWindow.return_value = 12345
        mock_win32.GetWindowText.return_value = "Test Window"
        result = handle_get_active_window()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["title"], "Test Window")

    @patch("engine.control.window_controller._get_visible_windows")
    def test_list_windows(self, mock_get):
        mock_get.return_value = [
            {"hwnd": 1, "title": "Window 1"},
            {"hwnd": 2, "title": "Window 2"},
        ]
        result = handle_list_windows()
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data["windows"]), 2)

    def test_handle_focus_window_missing(self):
        result = handle_focus_window()
        self.assertFalse(result.ok)

    @patch("engine.control.window_controller._get_visible_windows")
    @patch("engine.control.window_controller.win32gui")
    def test_handle_focus_window_found(self, mock_win32, mock_get):
        mock_get.return_value = [
            {"hwnd": 1, "title": "Google Chrome"},
            {"hwnd": 2, "title": "Notepad"},
        ]
        result = handle_focus_window(title="Chrome")
        self.assertTrue(result.ok)

    @patch("engine.control.window_controller._get_visible_windows")
    def test_handle_focus_window_not_found(self, mock_get):
        mock_get.return_value = [
            {"hwnd": 1, "title": "Some App"},
        ]
        result = handle_focus_window(title="NonExistent")
        self.assertFalse(result.ok)

    @patch("engine.control.window_controller.win32gui")
    def test_minimize_current(self, mock_win32):
        mock_win32.GetForegroundWindow.return_value = 123
        result = handle_minimize_window()
        self.assertTrue(result.ok)

    @patch("engine.control.window_controller._get_visible_windows")
    @patch("engine.control.window_controller.win32gui")
    def test_minimize_specific(self, mock_win32, mock_get):
        mock_get.return_value = [{"hwnd": 1, "title": "Chrome"}]
        result = handle_minimize_window(title="Chrome")
        self.assertTrue(result.ok)

    @patch("engine.control.window_controller.win32gui")
    def test_maximize_current(self, mock_win32):
        mock_win32.GetForegroundWindow.return_value = 123
        result = handle_maximize_window()
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
