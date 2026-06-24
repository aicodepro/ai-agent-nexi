import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from src.orin.control.safety import EmergencyStop, SandboxPolicy, AuditLog
from src.orin.control.base import ControlResult


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


if __name__ == "__main__":
    unittest.main()
