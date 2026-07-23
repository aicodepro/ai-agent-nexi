import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import threading
import time
from unittest.mock import patch, MagicMock
from engine.control.browser_session import BrowserSession
from engine.control.chrome_controller import (
    handle_open_chrome, handle_open_url, handle_search_google,
    handle_search_youtube, handle_open_youtube, handle_new_tab,
    handle_close_tab, handle_get_tab_info
)


def _fake_playwright_stack():
    page = MagicMock()
    page.is_closed.return_value = False
    page.url = "about:blank"
    context = MagicMock()
    context.is_closed.return_value = False
    context.new_page.return_value = page
    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch.return_value = browser
    starter = MagicMock()
    starter.start.return_value = playwright
    return starter, playwright, browser, context, page


class TestBrowserSession(unittest.TestCase):
    def tearDown(self):
        BrowserSession.close()

    @patch("playwright.sync_api.sync_playwright")
    def test_reuses_one_live_playwright_session_and_stops_it(self, mock_sync):
        starter, playwright, browser, context, page = _fake_playwright_stack()
        mock_sync.return_value = starter

        self.assertIs(BrowserSession.get_or_create_page(), page)
        self.assertIs(BrowserSession.get_or_create_page(), page)
        self.assertEqual(mock_sync.call_count, 1)

        BrowserSession.close()
        page.close.assert_called_once()
        context.close.assert_called_once()
        browser.close.assert_called_once()
        playwright.stop.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_concurrent_callers_create_only_one_session(self, mock_sync):
        starter, _playwright, _browser, _context, page = _fake_playwright_stack()

        def slow_start():
            time.sleep(0.02)
            return starter.start.return_value

        starter.start.side_effect = slow_start
        mock_sync.return_value = starter
        results = []
        threads = [threading.Thread(target=lambda: results.append(BrowserSession.get_or_create_page()))
                   for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(mock_sync.call_count, 1)
        self.assertEqual(results, [page] * 8)

    @patch("subprocess.Popen")
    @patch("engine.control.browser_session.os.system", side_effect=AssertionError("os.system used"))
    @patch("engine.control.browser_session.os.path.exists", return_value=True)
    def test_chrome_launch_is_non_shell_and_non_blocking(self, _exists, _system, mock_popen):
        self.assertTrue(BrowserSession.launch_chrome_process("https://example.com"))
        args, kwargs = mock_popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertIn("https://example.com", args[0])
        self.assertFalse(kwargs.get("shell", False))


class TestChromeController(unittest.TestCase):
    @patch("engine.control.chrome_controller.BrowserSession.launch_chrome_process")
    def test_handle_open_chrome_success(self, mock_launch):
        mock_launch.return_value = True
        result = handle_open_chrome()
        self.assertTrue(result.ok)

    @patch("engine.control.chrome_controller.BrowserSession.launch_chrome_process")
    def test_handle_open_chrome_with_url(self, mock_launch):
        mock_launch.return_value = True
        with patch("engine.control.chrome_controller.BrowserSession.navigate", return_value=None):
            result = handle_open_chrome(url="https://example.com")
        self.assertTrue(result.ok)

    def test_handle_open_url_missing(self):
        result = handle_open_url()
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "MISSING_ENTITY")

    @patch("engine.control.chrome_controller.BrowserSession.launch_chrome_process")
    @patch("engine.control.chrome_controller.BrowserSession.navigate")
    def test_handle_open_url(self, mock_nav, mock_launch):
        mock_nav.return_value = MagicMock()
        mock_launch.return_value = True
        result = handle_open_url(url="https://example.com")
        self.assertTrue(result.ok)

    @patch("engine.control.chrome_controller.BrowserSession.launch_chrome_process")
    @patch("engine.control.chrome_controller.BrowserSession.navigate")
    def test_handle_search_google(self, mock_nav, mock_launch):
        mock_nav.return_value = MagicMock()
        mock_launch.return_value = True
        result = handle_search_google(query="AI tools")
        self.assertTrue(result.ok)
        self.assertIn("AI tools", result.message)

    @patch("engine.control.chrome_controller.BrowserSession.navigate")
    def test_search_google_uses_standard_url_encoding(self, mock_nav):
        mock_nav.return_value = MagicMock()
        result = handle_search_google(query="AI tools & safety")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["url"], "https://www.google.com/search?q=AI+tools+%26+safety")

    def test_handle_search_google_missing(self):
        result = handle_search_google()
        self.assertFalse(result.ok)

    @patch("engine.control.chrome_controller.BrowserSession.launch_chrome_process")
    @patch("engine.control.chrome_controller.BrowserSession.navigate")
    def test_handle_search_youtube(self, mock_nav, mock_launch):
        mock_nav.return_value = MagicMock()
        mock_launch.return_value = True
        result = handle_search_youtube(query="AI tools")
        self.assertTrue(result.ok)
        self.assertIn("AI tools", result.message)

    def test_handle_search_youtube_missing(self):
        result = handle_search_youtube()
        self.assertFalse(result.ok)

    @patch("engine.control.chrome_controller.handle_open_url")
    def test_handle_open_youtube(self, mock_open_url):
        mock_open_url.return_value.ok = True
        result = handle_open_youtube()
        self.assertTrue(result.ok)

    @patch("engine.control.chrome_controller.pyautogui")
    @patch("engine.control.chrome_controller.BrowserSession.new_page", return_value=MagicMock())
    def test_handle_new_tab(self, _page, mock_pyautogui):
        result = handle_new_tab()
        self.assertTrue(result.ok)

    @patch("engine.control.chrome_controller.HAS_PYAUTOGUI", False)
    @patch("engine.control.chrome_controller.BrowserSession.new_page", return_value=None)
    def test_new_tab_reports_failure_when_no_path_works(self, _page):
        result = handle_new_tab()
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "NEW_TAB_FAILED")

    @patch("engine.control.chrome_controller.pyautogui")
    @patch("engine.control.chrome_controller.BrowserSession.close_current_page", return_value=True)
    def test_handle_close_tab(self, _close, mock_pyautogui):
        result = handle_close_tab()
        self.assertTrue(result.ok)

    @patch("engine.control.chrome_controller.HAS_PYAUTOGUI", False)
    @patch("engine.control.chrome_controller.BrowserSession.close_current_page", return_value=False)
    def test_close_tab_reports_failure_when_no_path_works(self, _page):
        result = handle_close_tab()
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "CLOSE_TAB_FAILED")

    @patch("webbrowser.open", return_value=False)
    @patch("engine.control.chrome_controller.BrowserSession.launch_chrome_process", return_value=False)
    @patch("engine.control.chrome_controller.BrowserSession.navigate", return_value=None)
    def test_open_url_reports_failure_when_all_paths_fail(self, _navigate, _launch, _web_open):
        result = handle_open_url(url="https://example.com")
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "URL_OPEN_FAILED")
        self.assertTrue(result.error["message"])

    @patch("engine.control.chrome_controller.BrowserSession.get_active_title")
    def test_handle_get_tab_info(self, mock_title):
        mock_title.return_value = "Chrome Tab"
        result = handle_get_tab_info()
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
