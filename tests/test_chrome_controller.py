import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from src.orin.control.chrome_controller import (
    handle_open_chrome, handle_open_url, handle_search_google,
    handle_search_youtube, handle_open_youtube, handle_new_tab,
    handle_close_tab, handle_get_tab_info
)


class TestChromeController(unittest.TestCase):
    @patch("src.orin.control.chrome_controller.BrowserSession.launch_chrome_process")
    def test_handle_open_chrome_success(self, mock_launch):
        mock_launch.return_value = True
        result = handle_open_chrome()
        self.assertTrue(result.ok)

    @patch("src.orin.control.chrome_controller.BrowserSession.launch_chrome_process")
    def test_handle_open_chrome_with_url(self, mock_launch):
        mock_launch.return_value = True
        result = handle_open_chrome(url="https://example.com")
        self.assertTrue(result.ok)

    def test_handle_open_url_missing(self):
        result = handle_open_url()
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "MISSING_ENTITY")

    @patch("src.orin.control.chrome_controller.BrowserSession.launch_chrome_process")
    @patch("src.orin.control.chrome_controller.BrowserSession.navigate")
    def test_handle_open_url(self, mock_nav, mock_launch):
        mock_nav.return_value = MagicMock()
        mock_launch.return_value = True
        result = handle_open_url(url="https://example.com")
        self.assertTrue(result.ok)

    @patch("src.orin.control.chrome_controller.BrowserSession.launch_chrome_process")
    @patch("src.orin.control.chrome_controller.BrowserSession.navigate")
    def test_handle_search_google(self, mock_nav, mock_launch):
        mock_nav.return_value = MagicMock()
        mock_launch.return_value = True
        result = handle_search_google(query="AI tools")
        self.assertTrue(result.ok)
        self.assertIn("AI tools", result.message)

    def test_handle_search_google_missing(self):
        result = handle_search_google()
        self.assertFalse(result.ok)

    @patch("src.orin.control.chrome_controller.BrowserSession.launch_chrome_process")
    @patch("src.orin.control.chrome_controller.BrowserSession.navigate")
    def test_handle_search_youtube(self, mock_nav, mock_launch):
        mock_nav.return_value = MagicMock()
        mock_launch.return_value = True
        result = handle_search_youtube(query="AI tools")
        self.assertTrue(result.ok)
        self.assertIn("AI tools", result.message)

    def test_handle_search_youtube_missing(self):
        result = handle_search_youtube()
        self.assertFalse(result.ok)

    @patch("src.orin.control.chrome_controller.handle_open_url")
    def test_handle_open_youtube(self, mock_open_url):
        mock_open_url.return_value.ok = True
        result = handle_open_youtube()
        self.assertTrue(result.ok)

    @patch("src.orin.control.chrome_controller.pyautogui")
    def test_handle_new_tab(self, mock_pyautogui):
        result = handle_new_tab()
        self.assertTrue(result.ok)

    @patch("src.orin.control.chrome_controller.pyautogui")
    def test_handle_close_tab(self, mock_pyautogui):
        result = handle_close_tab()
        self.assertTrue(result.ok)

    @patch("src.orin.control.chrome_controller.BrowserSession.get_active_title")
    def test_handle_get_tab_info(self, mock_title):
        mock_title.return_value = "Chrome Tab"
        result = handle_get_tab_info()
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
