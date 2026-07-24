import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from engine.control.base import ControlFunction, ControlResult
from engine.control.registry import ControlRegistry


def dummy_handler(**kwargs):
    return ControlResult.success(message="OK")


class TestControlRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ControlRegistry()
        self.registry.register(
            ControlFunction(
                name="open_app", intent="open application",
                description="Open app", risk_level="MEDIUM",
                handler=dummy_handler
            ),
            extra_keywords=["launch", "start", "open"]
        )
        self.registry.register(
            ControlFunction(
                name="list_apps", intent="list running applications",
                description="List apps", risk_level="SAFE",
                handler=dummy_handler
            ),
            extra_keywords=["running", "list"]
        )

    def test_get_by_name(self):
        func = self.registry.get("open_app")
        self.assertIsNotNone(func)
        self.assertEqual(func.name, "open_app")

    def test_get_missing(self):
        func = self.registry.get("nonexistent")
        self.assertIsNone(func)

    def test_match_by_exact_name(self):
        func = self.registry.match_by_text("open_app")
        self.assertIsNotNone(func)

    def test_match_by_intent(self):
        func = self.registry.match_by_text("open application")
        self.assertIsNotNone(func)
        self.assertEqual(func.name, "open_app")

    def test_match_by_keyword(self):
        func = self.registry.match_by_text("launch")
        self.assertIsNotNone(func)
        self.assertEqual(func.name, "open_app")

    def test_match_by_extra_keyword(self):
        func = self.registry.match_by_text("running")
        self.assertIsNotNone(func)
        self.assertEqual(func.name, "list_apps")

    def test_list_functions(self):
        funcs = self.registry.list_functions()
        self.assertEqual(len(funcs), 2)

    def test_has_function(self):
        self.assertTrue(self.registry.has_function("open_app"))
        self.assertFalse(self.registry.has_function("fake"))


class TestControlNLU(unittest.TestCase):
    def setUp(self):
        self.registry = ControlRegistry()
        self.registry.register(
            ControlFunction(
                name="open_app", intent="open application",
                description="", risk_level="MEDIUM", handler=dummy_handler
            ),
            extra_keywords=["launch", "start", "open"]
        )
        self.registry.register(
            ControlFunction(
                name="search_google", intent="search Google",
                description="", risk_level="MEDIUM", handler=dummy_handler
            ),
            extra_keywords=["google", "search web"]
        )
        self.registry.register(
            ControlFunction(
                name="search_youtube", intent="search YouTube",
                description="", risk_level="MEDIUM", handler=dummy_handler
            ),
            extra_keywords=["youtube", "you tube"]
        )
        self.registry.register(
            ControlFunction(
                name="get_active_window", intent="get active window",
                description="", risk_level="SAFE", handler=dummy_handler
            ),
            extra_keywords=["active window", "current window"]
        )
        self.registry.register(
            ControlFunction(
                name="create_folder", intent="create folder",
                description="", risk_level="MEDIUM", handler=dummy_handler
            ),
            extra_keywords=["make folder", "new folder"]
        )

    def test_open_chrome_nlu(self):
        func = self.registry.match_by_text("open chrome")
        self.assertIsNotNone(func)
        self.assertEqual(func.name, "open_app")

    def test_launch_chrome_nlu(self):
        func = self.registry.match_by_text("launch chrome")
        self.assertEqual(func.name, "open_app")

    def test_start_notepad_nlu(self):
        func = self.registry.match_by_text("start notepad")
        self.assertEqual(func.name, "open_app")

    def test_google_search_nlu(self):
        func = self.registry.match_by_text("search google for AI news")
        self.assertEqual(func.name, "search_google")

    def test_youtube_search_nlu(self):
        func = self.registry.match_by_text("search youtube for AI tools")
        self.assertEqual(func.name, "search_youtube")

    def test_active_window_nlu(self):
        func = self.registry.match_by_text("what window is active")
        self.assertEqual(func.name, "get_active_window")

    def test_current_window_nlu(self):
        func = self.registry.match_by_text("show current window")
        self.assertEqual(func.name, "get_active_window")

    def test_create_folder_nlu(self):
        func = self.registry.match_by_text("create folder on desktop")
        self.assertEqual(func.name, "create_folder")

    def test_make_folder_nlu(self):
        func = self.registry.match_by_text("make folder called test")
        self.assertEqual(func.name, "create_folder")

    def test_list_apps_nlu(self):
        self.registry.register(
            ControlFunction(
                name="list_apps", intent="list running applications",
                description="", risk_level="SAFE", handler=dummy_handler
            ),
            extra_keywords=["running", "list", "show apps"]
        )
        func = self.registry.match_by_text("show running apps")
        self.assertEqual(func.name, "list_apps")


if __name__ == "__main__":
    unittest.main()
