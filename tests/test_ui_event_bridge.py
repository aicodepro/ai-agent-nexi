import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ALLOWED_STATES = {
    "sleep", "listening", "thinking", "saying",
    "error", "online", "recognising", "waiting_for_speech",
}


class TestUiEventBridge:
    def test_set_state_valid(self):
        from engine.ui_event_bridge import set_state
        expected = {"wake_detected": "online"}
        for s in ALLOWED_STATES:
            result = set_state(s)
            want = expected.get(s, s)
            assert result["state"] == want

    def test_set_state_invalid_defaults_to_idle(self):
        from engine.ui_event_bridge import set_state
        result = set_state("banana")
        assert result["state"] == "sleep"

    def test_append_log_filters_level(self):
        from engine.ui_event_bridge import append_log
        result = append_log("banana", "test")
        assert result["level"] == "info"

    def test_append_log_valid_levels(self):
        from engine.ui_event_bridge import append_log
        for level in ("info", "warn", "error", "route", "tool", "voice"):
            result = append_log(level, "test")
            assert result["level"] == level

    def test_show_error(self):
        from engine.ui_event_bridge import show_error
        result = show_error("Something went wrong")
        assert result["state"] == "error"
        assert "Something went wrong" in result["text"]

    def test_speech_lifecycle(self):
        from engine.ui_event_bridge import speech_start, speech_stop
        assert speech_start()["state"] == "saying"
        assert speech_stop()["state"] == "sleep"

    def test_wake_detected(self):
        from engine.ui_event_bridge import wake_detected
        assert wake_detected()["state"] == "online"

    def test_sleeping(self):
        from engine.ui_event_bridge import sleeping
        assert sleeping()["state"] == "sleep"

    def test_append_user_message_ok(self):
        from engine.ui_event_bridge import append_user_message
        result = append_user_message("Hello")
        assert result["ok"] is True

    def test_append_assistant_message_ok(self):
        from engine.ui_event_bridge import append_assistant_message
        result = append_assistant_message("Response")
        assert result["ok"] is True
