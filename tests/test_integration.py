import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock

from engine.control import (
    execute_control_action, match_control_action, list_control_actions,
    EmergencyStop, registry
)
from engine.control.safety import SandboxPolicy
from engine.control.base import ControlResult


class TestIntegration(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()

    def test_safe_action_executes(self):
        result = execute_control_action("list_apps")
        self.assertTrue(result.ok)

    def test_get_active_window_executes(self):
        result = execute_control_action("get_active_window")
        self.assertTrue(result.ok)

    def test_unknown_action_fails(self):
        result = execute_control_action("xyznonexistent12345")
        self.assertFalse(result.ok)
        self.assertIn(result.error["code"], ["UNKNOWN_ACTION", "MISSING_ENTITY"])

    def test_emergency_stop_blocks_actions(self):
        EmergencyStop.engage(reason="test")
        result = execute_control_action("list_apps")
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "EMERGENCY_STOP")

    def test_emergency_stop_clear(self):
        EmergencyStop.engage(reason="test")
        EmergencyStop.clear()
        result = execute_control_action("list_apps")
        self.assertTrue(result.ok)

    def test_list_control_actions(self):
        actions = list_control_actions()
        self.assertGreater(len(actions), 0)
        names = [a["name"] for a in actions]
        self.assertIn("open_app", names)
        self.assertIn("list_apps", names)
        self.assertIn("get_active_window", names)

    def test_match_control_action_nlu(self):
        func = match_control_action("open chrome")
        if func:
            self.assertIn(func.name, ("open_app", "open_chrome"))

    def test_nlu_active_window(self):
        func = match_control_action("what window is active")
        if func:
            self.assertIn(func.name, ["get_active_window", "focus_window", "list_windows"])

    def test_nlu_search_google(self):
        func = match_control_action("google latest AI news")
        if func:
            self.assertEqual(func.name, "search_google")

    def test_sandbox_blocks_critical(self):
        allowed, reason = SandboxPolicy.is_allowed("CRITICAL", "delete_files")
        self.assertFalse(allowed)

    def test_sandbox_blocks_blocked_action(self):
        for action in SandboxPolicy.BLOCKED_ACTIONS:
            allowed, reason = SandboxPolicy.is_allowed("HIGH", action)
            self.assertFalse(allowed)

    def test_registry_lists_all_actions(self):
        expected_categories = ["open", "close", "list", "search", "get", "create", "focus"]
        actions = list_control_actions()
        all_names = " ".join(a["name"] for a in actions).lower()
        for cat in expected_categories:
            found = any(cat in a["name"].lower() for a in actions)
            self.assertTrue(found, f"Category '{cat}' not found in control actions")

    def test_control_functions_have_risk_levels(self):
        actions = list_control_actions()
        valid_risks = {"SAFE", "MEDIUM", "HIGH", "CRITICAL"}
        for action in actions:
            self.assertIn(action["risk_level"], valid_risks,
                          f"{action['name']} has invalid risk level: {action['risk_level']}")

    def test_open_app_executes(self):
        with patch("engine.control.process_controller.os.system") as mock_sys:
            mock_sys.return_value = 0
            result = execute_control_action("open_app", {"app_name": "notepad"})
            self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
