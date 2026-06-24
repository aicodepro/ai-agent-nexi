import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from src.orin.brain.intent_brain import IntentBrain
from src.orin.brain.bilingual_normalizer import BilingualNormalizer
from src.orin.brain.speech_recovery import SpeechRecovery
from src.orin.brain.action_planner import ActionPlanner
from src.orin.brain.action_verifier import ActionVerifier
from src.orin.control.safety import EmergencyStop


class TestIntentBrainEnglish(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.brain = IntentBrain()

    def test_open_chrome(self):
        result = self.brain.process("open chrome")
        self.assertIn(result.get("intent", ""), ["control_open_chrome", "open_app", "control_open_chrome_hi"])

    def test_open_browser(self):
        result = self.brain.process("open browser")
        self.assertIn(result.get("intent", ""), ["control_open_chrome", "open_app"])

    def test_open_youtube(self):
        result = self.brain.process("open youtube")
        self.assertIn(result.get("intent", ""), ["control_open_youtube", "control_open_youtube_hi", "youtube"])

    def test_search_youtube(self):
        result = self.brain.process("search youtube for AI tools")
        self.assertIn(result.get("intent", ""), ["control_search_youtube", "control_search_youtube_hi"])
        self.assertIn(result.get("entities", {}).get("query", ""), ["AI tools", "ai tools"])

    def test_search_google(self):
        result = self.brain.process("search google for AI news")
        self.assertIn(result.get("intent", ""), ["control_search_google", "control_search_google_hi"])

    def test_diagnose_jarvi(self):
        result = self.brain.process("diagnose jarvi")
        self.assertIn(result.get("intent", ""), ["diagnose_jarvi"])

    def test_stop_everything(self):
        result = self.brain.process("stop everything")
        self.assertIn(result.get("intent", ""), ["control_emergency_stop", "control_emergency_stop_hi"])

    def test_show_running_apps(self):
        result = self.brain.process("show running apps")
        self.assertIn(result.get("intent", ""), ["control_show_apps", "control_show_apps_hi"])

    def test_active_window(self):
        result = self.brain.process("what window is active")
        self.assertIn(result.get("intent", ""), ["control_active_window", "control_active_window_hi"])

    def test_empty_query(self):
        result = self.brain.process("")
        self.assertEqual(result.get("intent", ""), "")

    def test_none_query(self):
        result = self.brain.process(None)
        self.assertEqual(result.get("intent", ""), "")


class TestIntentBrainHindi(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.brain = IntentBrain()

    def test_chrome_kholo(self):
        result = self.brain.process("chrome kholo")
        self.assertIn(result.get("intent", ""), ["control_open_chrome", "control_open_chrome_hi"])

    def test_youtube_kholo(self):
        result = self.brain.process("youtube kholo")
        self.assertIn(result.get("intent", ""), ["control_open_youtube", "control_open_youtube_hi"])

    def test_google_pe_search_karo(self):
        result = self.brain.process("google pe AI news search karo")
        self.assertIn(result.get("intent", ""), ["control_search_google", "control_search_google_hi"])

    def test_youtube_pe_search_karo(self):
        result = self.brain.process("youtube pe search karo")
        self.assertIn(result.get("intent", ""), ["control_search_youtube", "control_search_youtube_hi"])

    def test_apps_dikhao(self):
        result = self.brain.process("apps dikhao")
        self.assertIn(result.get("intent", ""), ["control_show_apps", "control_show_apps_hi"])

    def test_sab_band_karo(self):
        result = self.brain.process("sab band karo")
        self.assertIn(result.get("intent", ""), ["control_emergency_stop", "control_emergency_stop_hi"])

    def test_folder_banao(self):
        result = self.brain.process("folder banao")
        self.assertIn(result.get("intent", ""), ["control_create_folder", "control_create_folder_hi"])

    def test_diagnose_karo(self):
        result = self.brain.process("jarvi diagnose karo")
        self.assertIn(result.get("intent", ""), ["diagnose_jarvi"])

    def test_downloads_kholo(self):
        result = self.brain.process("downloads kholo")
        self.assertIn(result.get("intent", ""), ["control_open_folder", "control_open_folder_hi"])


class TestBilingualNormalizer(unittest.TestCase):
    def test_chrome_kholo_normalization(self):
        normalized, lang, translations = BilingualNormalizer.normalize("chrome kholo")
        self.assertEqual(lang, "mixed")
        self.assertTrue(len(translations) > 0)

    def test_youtube_kholo_normalization(self):
        normalized, lang, translations = BilingualNormalizer.normalize("youtube kholo")
        self.assertEqual(lang, "mixed")

    def test_english_passthrough(self):
        normalized, lang, translations = BilingualNormalizer.normalize("open chrome")
        self.assertEqual(lang, "en")

    def test_detect_language_mixed(self):
        lang = BilingualNormalizer.detect_language("chrome kholo")
        self.assertEqual(lang, "mixed")

    def test_detect_language_english(self):
        lang = BilingualNormalizer.detect_language("open chrome")
        self.assertEqual(lang, "en")

    def test_get_hindi_patterns(self):
        patterns = BilingualNormalizer.get_hindi_patterns("control_open_chrome")
        self.assertIn("chrome kholo", patterns)

    def test_all_hindi_patterns(self):
        all_patterns = BilingualNormalizer.all_hindi_patterns()
        self.assertIn("control_open_chrome", all_patterns)

    def test_empty_text(self):
        normalized, lang, translations = BilingualNormalizer.normalize("")
        self.assertEqual(lang, "en")


class TestSpeechRecovery(unittest.TestCase):
    def test_send_male_correction(self):
        corrected, corrections = SpeechRecovery.recover("send male to rohit")
        self.assertIn("mail", corrected)

    def test_youTube_correction(self):
        corrected, corrections = SpeechRecovery.recover("open you tube")
        self.assertIn("youtube", corrected)

    def test_chrome_correction(self):
        corrected, corrections = SpeechRecovery.recover("open krom")
        self.assertIn("chrome", corrected)

    def test_jarvis_correction(self):
        corrected, corrections = SpeechRecovery.recover("diagnose jarvis")
        self.assertIn("jarvi", corrected)

    def test_stop_everything_correction(self):
        corrected, corrections = SpeechRecovery.recover("stop everthing")
        self.assertIn("everything", corrected)

    def test_no_correction_needed(self):
        corrected, corrections = SpeechRecovery.recover("open chrome")
        self.assertEqual(corrected, "open chrome")

    def test_empty_text(self):
        corrected, corrections = SpeechRecovery.recover("")
        self.assertEqual(corrected, "")

    def test_recover_query(self):
        result = SpeechRecovery.recover_query("open you tube")
        self.assertIn("youtube", result)


class TestActionPlanner(unittest.TestCase):
    def test_plan_open_chrome(self):
        plan = ActionPlanner.plan("control_open_chrome", confidence=0.9)
        self.assertEqual(plan["skill"], "browser")
        self.assertEqual(plan["function"], "open_chrome")
        self.assertEqual(plan["risk_level"], "MEDIUM")

    def test_plan_emergency_stop(self):
        plan = ActionPlanner.plan("control_emergency_stop", confidence=1.0)
        self.assertEqual(plan["function"], "emergency_stop")
        self.assertEqual(plan["risk_level"], "SAFE")

    def test_plan_missing_query(self):
        plan = ActionPlanner.plan("control_search_youtube", entities={}, confidence=0.8)
        self.assertIn("query", plan["missing_fields"])

    def test_plan_diagnose(self):
        plan = ActionPlanner.plan("diagnose_jarvi", confidence=0.9)
        self.assertEqual(plan["skill"], "diagnostics")
        self.assertEqual(plan["function"], "diagnose")


class TestActionVerifier(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()

    def test_verify_safe_action(self):
        result = {"risk_level": "SAFE", "function": "list_apps", "requires_confirmation": False}
        verified = ActionVerifier.verify(result)
        self.assertFalse(verified["requires_confirmation"])

    def test_verify_high_risk(self):
        result = {"risk_level": "HIGH", "function": "close_app", "requires_confirmation": False}
        verified = ActionVerifier.verify(result)
        self.assertTrue(verified["requires_confirmation"])

    def test_verify_emergency_stop_blocks(self):
        EmergencyStop.engage(reason="test")
        result = {"risk_level": "SAFE", "function": "list_apps", "requires_confirmation": False}
        verified = ActionVerifier.verify(result)
        self.assertEqual(verified["risk_level"], "CRITICAL")

    def test_is_executable_safe(self):
        result = {"risk_level": "SAFE", "function": "list_apps", "requires_confirmation": False}
        ok, reason = ActionVerifier.is_executable(result)
        self.assertTrue(ok)

    def test_is_executable_emergency_stop(self):
        EmergencyStop.engage(reason="test")
        result = {"risk_level": "SAFE", "function": "list_apps", "requires_confirmation": False}
        ok, reason = ActionVerifier.is_executable(result)
        self.assertFalse(ok)

    def test_is_executable_requires_confirmation(self):
        result = {"risk_level": "HIGH", "function": "close_app", "requires_confirmation": True}
        ok, reason = ActionVerifier.is_executable(result)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
