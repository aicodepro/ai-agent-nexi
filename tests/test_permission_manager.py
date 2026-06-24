import unittest
from unittest.mock import patch

from src.orin.control.permission_manager import PermissionManager
from src.orin.control.safety import EmergencyStop
from src.orin.vision.screen_trust import ScreenTrust


class TestPermissionManager(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        ScreenTrust.set_owner_trusted(False)
        self.pm = PermissionManager()

    def test_init(self):
        self.assertIsNotNone(self.pm)
        self.assertEqual(len(self.pm._pending_decisions), 0)

    def test_evaluate_safe_action_is_approved(self):
        result = self.pm.evaluate("run_diagnostics")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])

    def test_evaluate_medium_action_is_approved(self):
        result = self.pm.evaluate("open_application")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])

    def test_evaluate_high_action_requires_confirmation(self):
        result = self.pm.evaluate("screen_capture")
        self.assertEqual(result["decision"], "pending")
        self.assertTrue(result["requires_confirmation"])
        self.assertIn("screen", result["confirmation_prompt"].lower())

    def test_evaluate_critical_action_is_blocked(self):
        result = self.pm.evaluate("delete_files")
        self.assertEqual(result["decision"], "blocked")
        self.assertIn("sandbox", result["block_reason"].lower())

    def test_evaluate_emergency_stop_blocks_all(self):
        EmergencyStop.engage("test")
        result = self.pm.evaluate("run_diagnostics")
        self.assertEqual(result["decision"], "blocked")
        self.assertFalse(result["requires_confirmation"])
        EmergencyStop.clear()

    def test_evaluate_unknown_action_defaults_to_medium(self):
        result = self.pm.evaluate("some_random_action")
        self.assertEqual(result["risk_level"], "MEDIUM")
        self.assertEqual(result["decision"], "approved")

    def test_confirm_high_action_with_affirmative_yes(self):
        result = self.pm.confirm("screen_capture", "yes")
        self.assertEqual(result["decision"], "approved")
        self.assertTrue(result["user_confirmed"])

    def test_confirm_high_action_with_affirmative_y(self):
        result = self.pm.confirm("screen_capture", "y")
        self.assertEqual(result["decision"], "approved")
        self.assertTrue(result["user_confirmed"])

    def test_confirm_high_action_with_approve(self):
        result = self.pm.confirm("draft_email", "approve")
        self.assertEqual(result["decision"], "approved")
        self.assertTrue(result["user_confirmed"])

    def test_confirm_high_action_with_denial(self):
        result = self.pm.confirm("screen_capture", "no")
        self.assertEqual(result["decision"], "denied")
        self.assertFalse(result["user_confirmed"])
        self.assertIn("denied", result["block_reason"].lower())

    def test_confirm_high_action_with_empty_response(self):
        result = self.pm.confirm("screen_capture", "")
        self.assertEqual(result["decision"], "denied")
        self.assertFalse(result["user_confirmed"])

    def test_confirm_critical_action_remains_blocked_even_if_confirmed(self):
        result = self.pm.confirm("delete_files", "CONFIRM")
        self.assertEqual(result["decision"], "blocked")
        self.assertFalse(result["user_confirmed"])
        self.assertIn("sandbox", result["block_reason"].lower())

    def test_confirm_safe_action_auto_approved(self):
        result = self.pm.confirm("run_diagnostics", "yes")
        self.assertEqual(result["decision"], "approved")
        self.assertTrue(result["user_confirmed"])

    def test_require_confirmation_returns_prompt_for_high(self):
        prompt = self.pm.require_confirmation("screen_capture")
        self.assertIn("screen", prompt.lower())

    def test_require_confirmation_returns_prompt_for_critical(self):
        prompt = self.pm.require_confirmation("delete_files")
        self.assertIn("confirm", prompt.lower())

    def test_require_confirmation_returns_empty_for_safe(self):
        prompt = self.pm.require_confirmation("run_diagnostics")
        self.assertEqual(prompt, "")

    def test_evaluate_screen_capture_shows_correct_prompt(self):
        result = self.pm.evaluate("screen_capture")
        self.assertIn("capture", result["confirmation_prompt"].lower())
        self.assertIn("screen", result["confirmation_prompt"].lower())

    def test_confirm_under_emergency_stop_still_blocked(self):
        EmergencyStop.engage("stop test")
        result = self.pm.confirm("screen_capture", "yes")
        self.assertEqual(result["decision"], "blocked")
        self.assertIn("emergency stop", result["block_reason"].lower())
        EmergencyStop.clear()

    def test_evaluate_with_custom_risk_level(self):
        result = self.pm.evaluate("test_action", risk_level="SAFE")
        self.assertEqual(result["decision"], "approved")
        result2 = self.pm.evaluate("test_action", risk_level="HIGH")
        self.assertEqual(result2["decision"], "pending")
        self.assertTrue(result2["requires_confirmation"])

    def test_decision_contains_all_expected_keys(self):
        result = self.pm.evaluate("run_diagnostics")
        expected_keys = {
            "action_name", "risk_level", "decision", "requires_confirmation",
            "confirmation_prompt", "block_reason", "user_confirmed",
            "decision_id", "decision_timestamp", "confirmed_at",
            "owner_trusted",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_affirmative_allow_also_works(self):
        result = self.pm.confirm("screen_capture", "allow")
        self.assertEqual(result["decision"], "approved")
        self.assertTrue(result["user_confirmed"])

    def test_affirmative_ok_works(self):
        result = self.pm.confirm("screen_capture", "ok")
        self.assertEqual(result["decision"], "approved")

    def test_affirmative_proceed_works(self):
        result = self.pm.confirm("screen_capture", "proceed")
        self.assertEqual(result["decision"], "approved")

    def test_affirmative_numeric_1_works(self):
        result = self.pm.confirm("screen_capture", "1")
        self.assertEqual(result["decision"], "approved")

    def test_non_string_response_is_denied(self):
        result = self.pm.confirm("screen_capture", 1)
        self.assertEqual(result["decision"], "denied")

    def test_evaluate_high_action_creates_pending_decision(self):
        result = self.pm.evaluate("screen_capture")
        self.assertNotEqual(result["decision_id"], "")
        self.assertIn(result["decision_id"], self.pm._pending_decisions)

    def test_send_message_auto_is_critical(self):
        result = self.pm.evaluate("send_message_auto")
        self.assertEqual(result["risk_level"], "CRITICAL")
        self.assertEqual(result["decision"], "blocked")


if __name__ == "__main__":
    unittest.main()
