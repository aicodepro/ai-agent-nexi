import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from src.orin.control.file_controller import (
    handle_create_folder, handle_create_text_file, handle_open_folder,
    handle_search_files, add_safe_folder, _is_safe_path, SAFE_FOLDERS
)
from src.orin.control.base import ControlResult


class TestFileController(unittest.TestCase):
    def setUp(self):
        add_safe_folder(os.path.abspath(os.path.expanduser("~\\Desktop")))

    def test_create_folder_missing_name(self):
        result = handle_create_folder()
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "MISSING_ENTITY")

    @patch("src.orin.control.file_controller.os.makedirs")
    def test_create_folder_on_desktop(self, mock_makedirs):
        mock_makedirs.return_value = None
        result = handle_create_folder(folder_name="test_folder", location="desktop")
        self.assertTrue(result.ok)
        self.assertIn("test_folder", result.message)

    @patch("src.orin.control.file_controller.os.makedirs")
    def test_create_folder_in_downloads(self, mock_makedirs):
        mock_makedirs.return_value = None
        result = handle_create_folder(folder_name="test_folder", location="downloads")
        self.assertTrue(result.ok)

    def test_create_text_file_missing_name(self):
        result = handle_create_text_file()
        self.assertFalse(result.ok)

    @patch("builtins.open", new_callable=MagicMock)
    @patch("src.orin.control.file_controller.os.makedirs")
    def test_create_text_file(self, mock_makedirs, mock_open):
        mock_open.return_value.__enter__.return_value = MagicMock()
        result = handle_create_text_file(file_name="hello.txt", location="desktop", content="Hello World")
        self.assertTrue(result.ok)

    @patch("os.startfile")
    def test_open_folder_downloads(self, mock_start):
        result = handle_open_folder(location="downloads")
        self.assertTrue(result.ok)

    def test_open_folder_unknown(self):
        result = handle_open_folder(location="unknown_location")
        self.assertFalse(result.ok)

    @patch("os.startfile")
    def test_open_folder_desktop(self, mock_start):
        result = handle_open_folder(location="desktop")
        self.assertTrue(result.ok)

    def test_search_files_missing_name(self):
        result = handle_search_files()
        self.assertFalse(result.ok)

    @patch("src.orin.control.file_controller.os.walk")
    def test_search_files_found(self, mock_walk):
        mock_walk.return_value = [
            (os.path.expanduser("~\\Desktop"), [], ["test.txt", "other.txt"])
        ]
        result = handle_search_files(file_name="test")
        self.assertTrue(result.ok)

    def test_safe_path_check(self):
        safe = os.path.expanduser("~\\Desktop")
        self.assertTrue(_is_safe_path(safe))

    def test_unsafe_path_check(self):
        unsafe = "C:\\Windows\\System32"
        self.assertFalse(_is_safe_path(unsafe))


if __name__ == "__main__":
    unittest.main()
