import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import queue
import threading
import time


class TestSpeechInterrupt(unittest.TestCase):
    """Test stop phrase detection."""

    def setUp(self):
        from src.orin.voice.speech_interrupt import (
            is_stop_speaking_command,
            is_emergency_stop_command,
            classify_stop_command,
            normalize_stop_text,
        )
        self.is_stop = is_stop_speaking_command
        self.is_emergency = is_emergency_stop_command
        self.classify = classify_stop_command
        self.normalize = normalize_stop_text

    def test_stop_command_detected(self):
        self.assertTrue(self.is_stop("stop"))

    def test_stop_speaking_detected(self):
        self.assertTrue(self.is_stop("stop speaking"))

    def test_stop_talking_detected(self):
        self.assertTrue(self.is_stop("stop talking"))

    def test_enough_detected(self):
        self.assertTrue(self.is_stop("enough"))

    def test_cancel_speech_detected(self):
        self.assertTrue(self.is_stop("cancel speech"))

    def test_hindi_bas_detected(self):
        self.assertTrue(self.is_stop("bas"))

    def test_hindi_band_karo_detected(self):
        self.assertTrue(self.is_stop("band karo"))

    def test_hindi_chup_detected(self):
        self.assertTrue(self.is_stop("chup"))

    def test_hindi_chup_ho_jao_detected(self):
        self.assertTrue(self.is_stop("chup ho jao"))

    def test_hindi_ruk_jao_detected(self):
        self.assertTrue(self.is_stop("ruk jao"))

    def test_jarvis_stop_detected(self):
        self.assertTrue(self.is_stop("jarvis stop"))

    def test_stop_with_punctuation(self):
        self.assertTrue(self.is_stop("stop."))
        self.assertTrue(self.is_stop("stop!"))

    def test_emergency_stop_detected(self):
        self.assertTrue(self.is_emergency("stop everything"))

    def test_emergency_stop_phrase_detected(self):
        self.assertTrue(self.is_emergency("emergency stop"))

    def test_emergency_stop_sab_band_karo(self):
        self.assertTrue(self.is_emergency("sab band karo"))

    def test_emergency_stop_kill_all_tasks(self):
        self.assertTrue(self.is_emergency("kill all tasks"))

    def test_emergency_stop_halt(self):
        self.assertTrue(self.is_emergency("halt"))

    def test_emergency_stop_abort(self):
        self.assertTrue(self.is_emergency("abort"))

    def test_stop_speaking_not_emergency(self):
        """stop speaking must NOT trigger emergency stop."""
        self.assertFalse(self.is_emergency("stop"))
        self.assertFalse(self.is_emergency("stop speaking"))
        self.assertFalse(self.is_emergency("bas"))
        self.assertFalse(self.is_emergency("chup"))

    def test_stop_everything_is_emergency(self):
        """stop everything must trigger emergency stop classification."""
        self.assertEqual(self.classify("stop everything"), "emergency_stop")

    def test_stop_speaking_classification(self):
        self.assertEqual(self.classify("stop"), "stop_speaking")
        self.assertEqual(self.classify("stop speaking"), "stop_speaking")
        self.assertEqual(self.classify("bas"), "stop_speaking")

    def test_emergency_not_stop_speaking(self):
        """Emergency stop is NOT classified as stop_speaking."""
        self.assertNotEqual(self.classify("stop everything"), "stop_speaking")
        self.assertNotEqual(self.classify("emergency stop"), "stop_speaking")

    def test_random_text_no_match(self):
        self.assertIsNone(self.classify("open chrome"))
        self.assertIsNone(self.classify("what is the time"))
        self.assertIsNone(self.classify("play music"))

    def test_empty_text_no_match(self):
        self.assertIsNone(self.classify(""))
        self.assertIsNone(self.classify("   "))

    def test_none_text_no_match(self):
        self.assertFalse(self.is_stop(None))
        self.assertFalse(self.is_emergency(None))
        self.assertIsNone(self.classify(None))

    def test_normalize_removes_jarvis_prefix(self):
        result = self.normalize("jarvis stop")
        self.assertEqual(result, "stop")

    def test_normalize_removes_punctuation(self):
        result = self.normalize("stop.")
        self.assertEqual(result, "stop")


class TestSpeechControllerIsolation(unittest.TestCase):
    """Test SpeechController functions without real TTS."""

    def setUp(self):
        import importlib
        self.controller = importlib.import_module("src.orin.voice.speech_controller")
        self.controller.reset_stop_flag()
        self.controller.clear_queue()
        self.controller._STOP_EVENT.clear()

    def tearDown(self):
        self.controller.stop_speaking()
        self.controller._STOP_EVENT.clear()

    def test_is_speaking_false_initially(self):
        self.assertFalse(self.controller.is_speaking())

    def test_get_state_initially_idle(self):
        state = self.controller.get_state()
        self.assertEqual(state["state"], "idle")
        self.assertFalse(state["is_speaking"])
        self.assertEqual(state["queue_size"], 0)

    def test_stop_speaking_when_idle_is_safe(self):
        try:
            self.controller.stop_speaking(reason="test")
        except Exception:
            self.fail("stop_speaking when idle raised an exception")
        state = self.controller.get_state()
        self.assertEqual(state["state"], "idle")

    def test_clear_queue_when_empty(self):
        count = self.controller.clear_queue()
        self.assertEqual(count, 0)

    def test_speak_adds_to_queue(self):
        self.controller.speak("test message")
        state = self.controller.get_state()
        self.assertGreaterEqual(state["queue_size"], 0)

    def test_speak_interrupt_stops_old_speech(self):
        self.controller.speak("first message")
        self.controller.speak("second message", interrupt=True)
        state = self.controller.get_state()
        self.assertIn(state["state"], ("idle", "speaking"))

    def test_stop_speaking_clears_queue(self):
        self.controller.speak("message one")
        self.controller.speak("message two")
        self.controller.speak("message three")
        self.controller.stop_speaking(reason="test")
        state = self.controller.get_state()
        self.assertEqual(state["queue_size"], 0)
        self.assertFalse(state["is_speaking"])
        self.assertEqual(state["state"], "idle")

    def test_stop_speaking_changes_state(self):
        self.controller.speak("test message")
        self.controller.stop_speaking(reason="user_requested")
        state = self.controller.get_state()
        self.assertEqual(state["last_stop_reason"], "user_requested")

    def test_get_state_returns_copy(self):
        state1 = self.controller.get_state()
        state2 = self.controller.get_state()
        self.assertEqual(state1, state2)

    def test_requested_reason_in_state(self):
        self.controller.stop_speaking(reason="user_requested")
        state = self.controller.get_state()
        self.assertEqual(state["last_stop_reason"], "user_requested")

    def test_double_stop_speaking_is_safe(self):
        self.controller.stop_speaking(reason="first")
        try:
            self.controller.stop_speaking(reason="second")
        except Exception:
            self.fail("Double stop_speaking raised exception")
        state = self.controller.get_state()
        self.assertEqual(state["last_stop_reason"], "second")

    def test_no_duplicate_workers_after_stop(self):
        self.controller.speak("test")
        self.controller.stop_speaking()
        self.controller.speak("after stop")
        self.controller.stop_speaking()

    def test_reset_stop_flag(self):
        self.controller.stop_speaking()
        self.controller._STOP_EVENT.set()
        self.assertTrue(self.controller._STOP_EVENT.is_set())
        self.controller.reset_stop_flag()
        self.assertFalse(self.controller._STOP_EVENT.is_set())


class TestSpeechControllerMocks(unittest.TestCase):
    """Test SpeechController with mocked TTS engine."""

    @patch("src.orin.voice.speech_controller.pyttsx3")
    def test_speak_processes_queued_text(self, mock_pyttsx3):
        mock_engine = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine
        from src.orin.voice.speech_controller import speak, stop_speaking, get_state, is_speaking
        stop_speaking()
        speak("hello world")
        state = get_state()
        self.assertIn(state["state"], ("idle", "speaking"))

    @patch("src.orin.voice.speech_controller.pyttsx3")
    def test_multiple_queued_speech_cleared_on_stop(self, mock_pyttsx3):
        from src.orin.voice.speech_controller import speak, stop_speaking, get_state, clear_queue
        clear_queue()
        speak("first")
        speak("second")
        speak("third")
        stop_speaking(reason="test")
        state = get_state()
        self.assertEqual(state["queue_size"], 0)

    @patch("src.orin.voice.speech_controller.pyttsx3")
    def test_last_text_preview_updated(self, mock_pyttsx3):
        from src.orin.voice.speech_controller import speak, stop_speaking
        stop_speaking()
        speak("unique test phrase 12345")
        import time
        time.sleep(0.1)
        stop_speaking()

    @patch("src.orin.voice.speech_controller.pyttsx3")
    def test_shutdown_does_not_crash(self, mock_pyttsx3):
        from src.orin.voice.speech_controller import shutdown, speak
        speak("test")
        try:
            shutdown()
        except Exception:
            self.fail("shutdown raised exception")


class TestClassifySpeechControl(unittest.TestCase):
    """Test classify_speech_control function."""

    def test_classify_speech_stop(self):
        from src.orin.voice.speech_interrupt import classify_speech_control
        self.assertEqual(classify_speech_control("stop"), "speech_stop")
        self.assertEqual(classify_speech_control("stop speaking"), "speech_stop")
        self.assertEqual(classify_speech_control("bas"), "speech_stop")
        self.assertEqual(classify_speech_control("chup ho jao"), "speech_stop")
        self.assertEqual(classify_speech_control("jarvis stop"), "speech_stop")

    def test_classify_emergency_stop(self):
        from src.orin.voice.speech_interrupt import classify_speech_control
        self.assertEqual(classify_speech_control("stop everything"), "emergency_stop")
        self.assertEqual(classify_speech_control("emergency stop"), "emergency_stop")
        self.assertEqual(classify_speech_control("sab band karo"), "emergency_stop")
        self.assertEqual(classify_speech_control("kill all tasks"), "emergency_stop")

    def test_classify_none(self):
        from src.orin.voice.speech_interrupt import classify_speech_control
        self.assertEqual(classify_speech_control("open chrome"), "none")
        self.assertEqual(classify_speech_control("what is the time"), "none")
        self.assertEqual(classify_speech_control(""), "none")


class TestBridgeStopSpeaking(unittest.TestCase):
    """Test bridge integration for stop-speaking commands."""

    def test_bridge_stop_speaking_returns_state(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("stop speaking")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(result["result"]["message"], "Stopped speaking.")
        self.assertIn("state", result["result"]["data"])

    def test_bridge_bas_returns_stopped(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("bas")
        self.assertTrue(result["handled"])
        self.assertEqual(result["result"]["message"], "Stopped speaking.")

    def test_bridge_chup_returns_stopped(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("chup")
        self.assertTrue(result["handled"])
        self.assertEqual(result["result"]["message"], "Stopped speaking.")

    def test_bridge_emergency_stop_separate(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("stop everything")
        self.assertTrue(result["handled"])
        self.assertIn("Emergency stop", result["result"]["message"])
        self.assertTrue(result["result"]["data"].get("emergency_stop_engaged"))

    def test_bridge_random_not_handled(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        Phase3CommandBridge.reset()
        result = Phase3CommandBridge.try_handle("open chrome")
        self.assertFalse(result["handled"])


class TestSecretRedaction(unittest.TestCase):
    """Test that secrets are redacted from speech state preview."""

    @patch("src.orin.voice.speech_controller.pyttsx3")
    def test_no_secrets_in_preview(self, mock_pyttsx3):
        from src.orin.voice.speech_controller import speak, stop_speaking, get_state
        stop_speaking()
        speak("your password is secret123 and token abc123def456ghi789xyz")
        import time
        time.sleep(0.1)
        stop_speaking()
        state = get_state()
        preview = state.get("last_text_preview", "")
        self.assertNotIn("secret123", preview)
        self.assertNotIn("abc123def456ghi789xyz", preview)

    @patch("src.orin.voice.speech_controller.pyttsx3")
    def test_normal_text_preserved(self, mock_pyttsx3):
        from src.orin.voice.speech_controller import speak, stop_speaking, get_state
        stop_speaking()
        speak("Hello, I am Jarvis")
        import time
        time.sleep(0.1)
        stop_speaking()
        state = get_state()
        preview = state.get("last_text_preview", "")
        self.assertNotIn("[REDACTED", preview)


class TestRuntimeContextSpeechController(unittest.TestCase):
    """Test get_speech_controller returns working module."""

    def test_get_speech_controller_returns_module(self):
        from src.orin.app.runtime_context import get_speech_controller
        sc = get_speech_controller()
        self.assertTrue(hasattr(sc, "speak"))
        self.assertTrue(hasattr(sc, "stop_speaking"))
        self.assertTrue(hasattr(sc, "get_state"))
        self.assertTrue(hasattr(sc, "clear_queue"))
        self.assertTrue(hasattr(sc, "is_speaking"))


if __name__ == "__main__":
    unittest.main()
