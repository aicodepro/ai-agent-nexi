import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch
from src.orin.voice.response_style import ResponseStyle
from src.orin.voice.voice_personality import VoicePersonality
from src.orin.voice.voice_orchestrator import VoiceOrchestrator
from src.orin.control.safety import EmergencyStop


class TestResponseStyle(unittest.TestCase):
    def test_acknowledgement_en(self):
        result = ResponseStyle.format("acknowledgement", "Opening Chrome.", "en")
        self.assertIn("Opening Chrome", result)

    def test_success_en(self):
        result = ResponseStyle.format("success", "Done.", "en")
        self.assertIn("Done", result)

    def test_blocked_en(self):
        result = ResponseStyle.format("blocked", "Action blocked.", "en")
        self.assertIn("blocked", result.lower())

    def test_confirmation_en(self):
        result = ResponseStyle.format("confirmation", "Proceed?", "en")
        self.assertIn("Proceed", result)

    def test_error_en(self):
        result = ResponseStyle.format("error", "Failed.", "en")
        self.assertIn("Failed", result)

    def test_thinking_en(self):
        result = ResponseStyle.format("thinking", "Checking.", "en")
        self.assertIn("Checking", result)

    def test_executing_en(self):
        result = ResponseStyle.format("executing", "Working.", "en")
        self.assertIn("Working", result)

    def test_get_styles(self):
        styles = ResponseStyle.get_styles()
        self.assertIn("acknowledgement", styles)
        self.assertIn("success", styles)
        self.assertIn("blocked", styles)
        self.assertIn("error", styles)
        self.assertIn("confirmation", styles)

    def test_unknown_language_falls_back(self):
        result = ResponseStyle.format("success", "Done.", "fr")
        self.assertIn("Done", result)

    def test_mixed_language(self):
        result = ResponseStyle.format("success", "Done.", "mixed")
        self.assertIn("Done", result)


class TestVoicePersonality(unittest.TestCase):
    def test_style_success(self):
        result = VoicePersonality.style("success", "Opening Chrome.", "en")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_style_blocked(self):
        result = VoicePersonality.style("blocked", "Stopped.", "en")
        self.assertIn("Stopped", result)

    def test_get_personality(self):
        self.assertEqual(VoicePersonality.get_personality("acknowledgement"), "concise")
        self.assertEqual(VoicePersonality.get_personality("blocked"), "firm")
        self.assertEqual(VoicePersonality.get_personality("unknown"), "neutral")


class TestVoiceOrchestrator(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()

    def test_compose_success(self):
        intent_result = {
            "function": "open_chrome",
            "risk_level": "MEDIUM",
            "requires_confirmation": False,
            "user_facing_summary": "Opening Chrome.",
            "language": "en",
            "missing_fields": [],
        }
        result = VoiceOrchestrator.compose(intent_result)
        self.assertIn("Chrome", result)

    def test_compose_blocked_by_emergency_stop(self):
        EmergencyStop.engage(reason="test")
        intent_result = {
            "function": "open_chrome",
            "risk_level": "MEDIUM",
            "requires_confirmation": False,
            "user_facing_summary": "Opening Chrome.",
            "language": "en",
            "missing_fields": [],
        }
        result = VoiceOrchestrator.compose(intent_result)
        self.assertIn("Stopped", result)
        EmergencyStop.clear()

    def test_compose_critical_action(self):
        intent_result = {
            "function": "delete_files",
            "risk_level": "CRITICAL",
            "requires_confirmation": False,
            "user_facing_summary": "Blocked: delete is not allowed.",
            "language": "en",
            "missing_fields": [],
        }
        result = VoiceOrchestrator.compose(intent_result)
        self.assertIn("blocked", result.lower())

    def test_compose_needs_confirmation(self):
        intent_result = {
            "function": "close_app",
            "risk_level": "HIGH",
            "requires_confirmation": True,
            "user_facing_summary": "Closing the app.",
            "follow_up_question": "Should I proceed?",
            "language": "en",
            "missing_fields": [],
        }
        result = VoiceOrchestrator.compose(intent_result)
        self.assertIn("proceed", result.lower())

    def test_compose_missing_fields(self):
        intent_result = {
            "function": "search_youtube",
            "risk_level": "MEDIUM",
            "requires_confirmation": False,
            "user_facing_summary": "Searching YouTube.",
            "follow_up_question": "What should I search for?",
            "language": "en",
            "missing_fields": ["query"],
        }
        result = VoiceOrchestrator.compose(intent_result)
        self.assertTrue(len(result) > 0)

    def test_compose_error(self):
        result = VoiceOrchestrator.compose_error("Something went wrong", "en")
        self.assertIn("wrong", result.lower())

    def test_compose_none_result(self):
        result = VoiceOrchestrator.compose(None)
        self.assertTrue(len(result) > 0)


if __name__ == "__main__":
    unittest.main()
