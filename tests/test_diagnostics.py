import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor, run_all_checks, CHECK_RESULTS
from engine.diagnostic_doctors.bridge_doctor import BridgeDoctor
from engine.diagnostic_doctors.hotword_doctor import HotwordDoctor
from engine.diagnostic_doctors.playwright_doctor import PlaywrightDoctor


class TestRuntimeDoctor(unittest.TestCase):
    def test_diagnose_returns_result(self):
        result = RuntimeDoctor.diagnose()
        self.assertIn("ok", result)
        self.assertIn("checks", result)
        self.assertIn("summary", result)
        self.assertIn("timestamp", result)

    def test_diagnose_has_all_checks(self):
        result = RuntimeDoctor.diagnose()
        check_names = [c["name"] for c in result["checks"]]
        self.assertIn("Bridge", check_names)
        self.assertIn("Hotword/Speech", check_names)
        self.assertIn("Playwright", check_names)
        self.assertIn("Dependencies", check_names)
        self.assertIn("Computer-Use Harness", check_names)
        self.assertIn("Tool Verifier Layer", check_names)

    def test_format_diagnosis(self):
        result = RuntimeDoctor.diagnose()
        report = RuntimeDoctor.format_diagnosis(result)
        self.assertIn("Nexi Diagnostics", report)

    def test_check_hotword(self):
        result = RuntimeDoctor.check_hotword()
        self.assertIn("name", result)
        self.assertEqual(result["name"], "Hotword/Speech")

    def test_check_bridge(self):
        result = RuntimeDoctor.check_bridge()
        self.assertIn("name", result)
        self.assertEqual(result["name"], "Bridge")

    def test_check_playwright(self):
        result = RuntimeDoctor.check_playwright()
        self.assertIn("name", result)
        self.assertEqual(result["name"], "Playwright")

    def test_check_capability(self):
        result = RuntimeDoctor.check_capability("tool verifier layer")
        self.assertIn("name", result)
        self.assertEqual(result["name"], "Tool Verifier Layer")
        self.assertIn("role", result)
        self.assertIn("safety_policy", result)

    def test_migrated_model_router_and_mark_hud_are_healthy(self):
        checks = {item["name"]: item for item in RuntimeDoctor.diagnose()["checks"]}
        self.assertTrue(checks["Model Router"]["ok"], checks["Model Router"])
        self.assertTrue(checks["Conscious HUD"]["ok"], checks["Conscious HUD"])

    def test_log_error(self):
        RuntimeDoctor._last_errors = []
        RuntimeDoctor.log_error("test error", context="test")
        errors = RuntimeDoctor.get_last_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["message"], "test error")

    def test_log_error_limit(self):
        RuntimeDoctor._last_errors = []
        for i in range(60):
            RuntimeDoctor.log_error(f"error {i}")
        errors = RuntimeDoctor.get_last_errors()
        self.assertLessEqual(len(errors), 50)


class TestBridgeDoctor(unittest.TestCase):
    def test_check(self):
        result = BridgeDoctor.check()
        self.assertIn("name", result)

    def test_is_control_available(self):
        result = BridgeDoctor.is_control_available()
        self.assertIsInstance(result, bool)


class TestHotwordDoctor(unittest.TestCase):
    def test_check(self):
        result = HotwordDoctor.check()
        self.assertIn("name", result)

    def test_is_speech_recognition_available(self):
        result = HotwordDoctor.is_speech_recognition_available()
        self.assertIsInstance(result, bool)


class TestPlaywrightDoctor(unittest.TestCase):
    def test_check(self):
        result = PlaywrightDoctor.check()
        self.assertIn("name", result)

    def test_is_available(self):
        result = PlaywrightDoctor.is_available()
        self.assertIsInstance(result, bool)

    @patch("engine.diagnostic_doctors.playwright_doctor.PlaywrightDoctor.is_available")
    def test_can_launch_when_not_available(self, mock_avail):
        mock_avail.return_value = False
        ok, reason = PlaywrightDoctor.can_launch()
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
