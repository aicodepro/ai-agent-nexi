import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock


class TestEmergencyStopPriority(unittest.TestCase):
    """Bug 1: Emergency stop must be checked before speech stop."""

    def test_emergency_stop_detected_first(self):
        from src.orin.voice.speech_interrupt import (
            is_emergency_stop_command,
            is_stop_speaking_command,
            classify_stop_command,
        )
        self.assertTrue(is_emergency_stop_command("stop everything"))
        self.assertTrue(is_emergency_stop_command("emergency stop"))
        self.assertTrue(is_emergency_stop_command("sab band karo"))
        self.assertTrue(is_emergency_stop_command("kill all tasks"))

    def test_emergency_stop_matches_in_phrase(self):
        from src.orin.voice.speech_interrupt import is_emergency_stop_command
        self.assertTrue(is_emergency_stop_command("stop everything right now"))
        self.assertTrue(is_emergency_stop_command("please stop everything"))
        self.assertTrue(is_emergency_stop_command("emergency stop now"))
        self.assertTrue(is_emergency_stop_command("I said sab band karo"))

    def test_stop_speaking_not_emergency(self):
        from src.orin.voice.speech_interrupt import is_emergency_stop_command
        self.assertFalse(is_emergency_stop_command("stop"))
        self.assertFalse(is_emergency_stop_command("stop speaking"))
        self.assertFalse(is_emergency_stop_command("bas"))
        self.assertFalse(is_emergency_stop_command("chup"))

    def test_stop_everything_not_stop_speaking(self):
        from src.orin.voice.speech_interrupt import is_stop_speaking_command
        self.assertFalse(is_stop_speaking_command("stop everything"))

    def test_classify_emergency_before_stop_speaking(self):
        from src.orin.voice.speech_interrupt import classify_stop_command
        self.assertEqual(classify_stop_command("stop everything"), "emergency_stop")

    def test_bridge_emergency_stop_separate(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("stop everything")
        self.assertTrue(result["handled"])
        self.assertIn("Emergency stop", result["result"]["message"])
        self.assertTrue(result["result"]["data"].get("emergency_stop_engaged"))

    def test_bridge_random_not_emergency(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("stop speaking")
        self.assertTrue(result["handled"])
        self.assertEqual(result["result"]["message"], "Stopped speaking.")
        self.assertNotIn("emergency", result["result"]["data"])

    def test_bridge_bas_not_emergency(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("bas")
        self.assertTrue(result["handled"])
        self.assertEqual(result["result"]["message"], "Stopped speaking.")


class TestCreateCommandRouting(unittest.TestCase):
    """Bug 2: 'create essay/story/article' must NOT route to create_folder."""

    def test_match_intent_create_essay(self):
        from engine.intents import match_intent
        intent, score = match_intent("I want you to create a essay on AI")
        if intent:
            self.assertNotEqual(intent.name, "create_folder", "create essay should not match create_folder")
            self.assertNotEqual(intent.name, "create_file", "create essay should not match create_file")

    def test_match_intent_create_story(self):
        from engine.intents import match_intent
        intent, score = match_intent("create a story about robots")
        if intent:
            self.assertNotEqual(intent.name, "create_folder")

    def test_match_intent_create_content(self):
        from engine.intents import match_intent
        intent, score = match_intent("create content about AI")
        if intent:
            self.assertNotEqual(intent.name, "create_folder")

    def test_match_intent_write_essay(self):
        from engine.intents import match_intent
        intent, score = match_intent("write a essay on AI")
        if intent:
            self.assertNotEqual(intent.name, "create_folder")
            self.assertNotEqual(intent.name, "create_file")

    def test_match_intent_create_folder_named(self):
        from engine.intents import match_intent
        intent, score = match_intent("create folder named test")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.name, "create_folder")

    def test_match_intent_make_folder(self):
        from engine.intents import match_intent
        intent, score = match_intent("make folder for my project")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.name, "create_folder")

    def test_match_intent_create_file_named(self):
        from engine.intents import match_intent
        intent, score = match_intent("create file named notes")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.name, "create_file")

    def test_create_folder_routes_correctly(self):
        from engine.command import dispatch_intent
        try:
            from src.orin.control.safety import EmergencyStop
            EmergencyStop.clear()
        except ImportError:
            pass
        with patch("engine.command.create_folder_and_files") as mock_cff:
            with patch("engine.command.speak"):
                result = dispatch_intent("create folder named test and add a file inside")
                self.assertTrue(result)
                mock_cff.assert_called_once()

    def test_create_essay_does_not_call_create_folder(self):
        from engine.command import dispatch_intent
        with patch("engine.command.create_folder_and_files") as mock_cff:
            with patch("engine.command.speak"):
                result = dispatch_intent("I want you to create a essay on AI")
                mock_cff.assert_not_called()

    def test_write_essay_does_not_call_create_folder(self):
        from engine.command import dispatch_intent
        with patch("engine.command.create_folder_and_files") as mock_cff:
            with patch("engine.command.speak"):
                result = dispatch_intent("write a essay on AI")
                mock_cff.assert_not_called()


class TestNoneResponseGuard(unittest.TestCase):
    """Bug 3: None response from chat/write path is handled safely."""

    def test_chatBot_handles_none_response(self):
        with patch("engine.gemini_brain.ask_gemini", return_value=None):
            with patch("engine.features.speak") as mock_speak:
                from engine.features import chatBot
                import engine.features as features
                features._brain_fail_until = 0.0
                result = chatBot("write a essay on AI")
                self.assertIsInstance(result, str)

    def test_chatBot_handles_valid_response(self):
        with patch("engine.gemini_brain.ask_gemini", return_value="Here is your essay"):
            with patch("engine.features.speak") as mock_speak:
                from engine.features import chatBot
                import engine.features as features
                features._brain_fail_until = 0.0
                result = chatBot("write a essay on AI")
                self.assertEqual(result, "Here is your essay")

    def test_allCommands_never_crashes_for_user_reported(self):
        with patch("engine.command.speak"):
            with patch("engine.command.takecommand", return_value=""):
                with patch("engine.command._store_conversation_turn"):
                    with patch("engine.command.eel") as mock_eel:
                        from engine.command import allCommands
                        try:
                            allCommands("I want you to create")
                            allCommands("I want you to create a essay on AI")
                            allCommands("write a essay on AI")
                        except Exception as e:
                            self.fail(f"allCommands raised exception: {e}")

    def test_store_conversation_guarded(self):
        from engine.command import _store_conversation_turn
        try:
            _store_conversation_turn("test query", None)
            _store_conversation_turn(None, "test response")
            _store_conversation_turn(None, None)
        except Exception as e:
            self.fail(f"_store_conversation_turn raised: {e}")


class TestScreenDekhoFallback(unittest.TestCase):
    """Bug 4: screen dekho returns graceful fallback."""

    def test_unknown_context_message(self):
        from src.orin.vision.vision_analyzer import VisionAnalyzer
        analyzer = VisionAnalyzer()
        result = analyzer.analyze({"visible_text": ""})
        self.assertIn("summary", result)
        self.assertNotIn("could not be classified", result["summary"])
        self.assertTrue(result["summary"].startswith("I cannot identify"))

    def test_classify_unknown_returns_graceful_message(self):
        from src.orin.vision.vision_analyzer import VisionAnalyzer
        analyzer = VisionAnalyzer()
        result = analyzer.analyze({"visible_text": "some random text without keywords"})
        self.assertEqual(result["detected_context"], "unknown")
        self.assertTrue(result["summary"].startswith("I cannot identify"))

    def test_classify_code_unchanged(self):
        from src.orin.vision.vision_analyzer import VisionAnalyzer
        analyzer = VisionAnalyzer()
        result = analyzer.analyze({"visible_text": "def hello(): import os"})
        self.assertEqual(result["detected_context"], "code")
        self.assertEqual(result["summary"], "The screen shows code content.")


if __name__ == "__main__":
    unittest.main()
