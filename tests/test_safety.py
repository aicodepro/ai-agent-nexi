import sys

import pytest
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch
from engine.control.safety import EmergencyStop, SandboxPolicy, AuditLog
from engine.control.base import ControlResult


@pytest.fixture(autouse=True)
def _enable_safety_gate(monkeypatch):
    """conftest defaults SAFETY_GATE_ENABLED=false for the suite (the gate is a live
    network classifier). This file tests the gate itself, so turn it on."""
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "true")




class TestEmergencyStop(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()

    def test_not_engaged_by_default(self):
        self.assertFalse(EmergencyStop.is_engaged())

    def test_engage(self):
        EmergencyStop.engage(reason="test stop")
        self.assertTrue(EmergencyStop.is_engaged())
        self.assertEqual(EmergencyStop.reason(), "test stop")

    def test_clear(self):
        EmergencyStop.engage(reason="test")
        EmergencyStop.clear()
        self.assertFalse(EmergencyStop.is_engaged())
        self.assertEqual(EmergencyStop.reason(), "")

    def test_engage_blocks_multiple(self):
        EmergencyStop.engage(reason="first")
        EmergencyStop.engage(reason="second")
        self.assertEqual(EmergencyStop.reason(), "second")


class TestSandboxPolicy(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()

    def test_safe_allowed(self):
        allowed, reason = SandboxPolicy.is_allowed("SAFE", "list_apps")
        self.assertTrue(allowed)

    def test_medium_allowed(self):
        allowed, reason = SandboxPolicy.is_allowed("MEDIUM", "open_app")
        self.assertTrue(allowed)

    def test_critical_blocked(self):
        allowed, reason = SandboxPolicy.is_allowed("CRITICAL", "delete_files")
        self.assertFalse(allowed)

    def test_blocked_action_list(self):
        for action in SandboxPolicy.BLOCKED_ACTIONS:
            allowed, reason = SandboxPolicy.is_allowed("HIGH", action)
            self.assertFalse(allowed, f"{action} should be blocked")

    def test_emergency_stop_blocks_all(self):
        EmergencyStop.engage(reason="stop")
        allowed, reason = SandboxPolicy.is_allowed("SAFE", "list_apps")
        self.assertFalse(allowed)
        self.assertIn("Emergency stop", reason)

    def test_requires_confirmation(self):
        self.assertFalse(SandboxPolicy.requires_confirmation("SAFE"))
        self.assertFalse(SandboxPolicy.requires_confirmation("MEDIUM"))
        self.assertTrue(SandboxPolicy.requires_confirmation("HIGH"))
        self.assertTrue(SandboxPolicy.requires_confirmation("CRITICAL"))


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        AuditLog.clear_log()
        AuditLog.set_enabled(True)

    def test_log_entry(self):
        AuditLog.log("test_action", {"key": "val"}, ControlResult.success())
        log = AuditLog.get_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action"], "test_action")
        self.assertEqual(log[0]["entities"]["key"], "val")

    def test_log_disabled(self):
        AuditLog.set_enabled(False)
        AuditLog.log("test_action")
        self.assertEqual(len(AuditLog.get_log()), 0)

    def test_log_limit(self):
        for i in range(100):
            AuditLog.log(f"action_{i}")
        log = AuditLog.get_log(limit=5)
        self.assertLessEqual(len(log), 5)

    def test_clear_log(self):
        AuditLog.log("test")
        AuditLog.clear_log()
        self.assertEqual(len(AuditLog.get_log()), 0)


class TestSafetyProviderFailures(unittest.TestCase):
    def test_missing_provider_key_fails_closed_for_action_route(self):
        from engine.safety_gate import execution_is_safe

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            decision = execution_is_safe("create_folder", {"folder_name": "test"})

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["risk"], "blocked")

    def test_provider_error_fails_closed_for_action_route(self):
        from engine.safety_gate import execution_is_safe

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch(
            "engine.safety_gate.requests.post", side_effect=TimeoutError("timeout")
        ):
            decision = execution_is_safe("create_folder", {"folder_name": "test"})

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["risk"], "blocked")

    def test_true_qa_does_not_require_action_confirmation_without_provider(self):
        from engine.safety_gate import classify_safety

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            decision = classify_safety("What is an API key?", context={"route": "brain"})

        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["requires_confirmation"])

    def test_malformed_provider_decision_fails_closed_for_action_route(self):
        from engine.safety_gate import execution_is_safe

        response = unittest.mock.MagicMock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch(
            "engine.safety_gate.requests.post", return_value=response
        ):
            decision = execution_is_safe("create_folder", {"folder_name": "test"})

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["risk"], "blocked")


if __name__ == "__main__":
    unittest.main()
