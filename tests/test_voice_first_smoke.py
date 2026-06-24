import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
from engine.hotword_helper import (
    is_jarvis_hotword,
    check_hotword_cooldown,
    reset_hotword_cooldown,
    HOTWORD_COOLDOWN_SECONDS,
)


class TestVoiceFirstSmoke(unittest.TestCase):
    """Smoke tests verifying the voice-first call chain without hardware."""

    def test_chat_hello_calls_speak_once(self):
        from engine.command import allCommands
        with patch("engine.features.chatBot") as mock_chat:
            mock_chat.return_value = "Hello! How can I help you?"
            with patch("engine.command.eel") as mock_eel:
                with patch("engine.command.speak") as mock_speak:
                    allCommands("hello")
                    mock_speak.assert_called_once()

    def test_chat_hello_shows_hood(self):
        from engine.command import allCommands
        with patch("engine.features.chatBot") as mock_chat:
            mock_chat.return_value = "Hello!"
            with patch("engine.command.eel") as mock_eel:
                with patch("engine.command.speak"):
                    allCommands("hello")
                    mock_eel.ShowHood.assert_called_once()

    def test_hotword_jarvis_triggers_wake(self):
        self.assertTrue(is_jarvis_hotword("jarvis"))
        self.assertTrue(is_jarvis_hotword("hey jarvis"))
        self.assertTrue(is_jarvis_hotword("jervis"))

    def test_hotword_jar_does_not_trigger(self):
        self.assertFalse(is_jarvis_hotword("jar"))
        self.assertFalse(is_jarvis_hotword("jars"))

    def test_hotword_no_false_positive_on_jar_repeated(self):
        for _ in range(10):
            self.assertFalse(is_jarvis_hotword("jar"))

    def test_hotword_cooldown_blocks_repeat_immediately(self):
        reset_hotword_cooldown()
        self.assertTrue(check_hotword_cooldown())
        for _ in range(5):
            self.assertFalse(check_hotword_cooldown())


if __name__ == "__main__":
    unittest.main()
