import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_barge_in_interrupts_when_speaking(monkeypatch):
    from engine.barge_in_manager import get_barge_in_manager, reset_barge_in_state
    from engine.interrupt_controller import set_speaking, clear_interrupt

    monkeypatch.setenv("BARGE_IN_ENABLED", "true")
    reset_barge_in_state()
    clear_interrupt()
    set_speaking(True)
    with patch("engine.interrupt_controller.request_interrupt") as req, \
         patch("engine.turn_manager.request_interrupt") as turn_req, \
         patch("engine.groq_tts.stop", return_value=True) as stop:
        result = get_barge_in_manager().interrupt(source="hotword", reason="wake_detected", speech_ms=300)

    assert result.interrupted is True
    assert result.level == "pause"
    req.assert_called_once()
    turn_req.assert_called_once()
    stop.assert_called_once()
    set_speaking(False)


def test_barge_in_debounces_repeated_interrupt(monkeypatch):
    from engine.barge_in_manager import get_barge_in_manager, reset_barge_in_state
    from engine.interrupt_controller import set_speaking

    monkeypatch.setenv("BARGE_IN_ENABLED", "true")
    monkeypatch.setenv("BARGE_IN_DEBOUNCE_MS", "5000")
    reset_barge_in_state()
    set_speaking(True)
    with patch("engine.interrupt_controller.request_interrupt"), \
         patch("engine.turn_manager.request_interrupt"), \
         patch("engine.groq_tts.stop", return_value=True):
        first = get_barge_in_manager().interrupt(source="hotword", speech_ms=2000)
        second = get_barge_in_manager().interrupt(source="hotword", speech_ms=2000)

    assert first.interrupted is True
    assert first.level == "cancel"
    assert second.interrupted is False
    assert second.reason == "debounced"
    set_speaking(False)


def test_barge_in_ignores_short_speech(monkeypatch):
    from engine.barge_in_manager import get_barge_in_manager, reset_barge_in_state
    from engine.interrupt_controller import set_speaking

    monkeypatch.setenv("BARGE_IN_MIN_SPEECH_MS", "200")
    reset_barge_in_state()
    set_speaking(True)
    result = get_barge_in_manager().interrupt(source="hotword", speech_ms=50)
    assert result.interrupted is False
    assert result.reason == "speech_too_short"
    set_speaking(False)


def test_groq_tts_stop_stops_registered_handle():
    from engine import groq_tts

    class Handle:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    handle = Handle()
    groq_tts._current_play_handle = handle
    assert groq_tts.stop() is True
    assert handle.stopped is True


def test_runtime_bridge_interrupted_maps_to_listening():
    from engine.runtime_bridge import EVENT_INTERRUPTED, STATUS_TO_UI_STATE

    assert STATUS_TO_UI_STATE[EVENT_INTERRUPTED] == "listening"
