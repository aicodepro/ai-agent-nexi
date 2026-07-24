import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _states(update):
    return [call.args[0]["state"] for call in update.call_args_list]


def test_required_voice_ui_status_sequence():
    from engine.runtime_bridge import handle_bridge_event

    events = [
        {"type": "status", "status": "wake_detected", "source": "hotword"},
        {"type": "status", "status": "listening_started", "source": "hotword"},
        {"type": "status", "status": "speech_ended", "source": "hotword"},
        {"type": "status", "status": "asr_started", "source": "hotword"},
        {"type": "status", "status": "asr_result", "source": "hotword", "text": "what is AI"},
    ]
    with patch("eel.updateNexiState", create=True) as update, patch("eel.senderText", create=True):
        for event in events:
            handle_bridge_event(event)
    assert _states(update) == ["online", "listening", "recognising", "recognising", "recognising", "thinking"]


def test_tts_status_sequence_maps_to_speaking_and_online():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateNexiState", create=True) as update:
        handle_bridge_event({"type": "status", "status": "speaking_started", "source": "tts"})
        handle_bridge_event({"type": "status", "status": "idle", "source": "tts"})
    assert _states(update) == ["saying", "sleep"]


def test_speech_started_drives_recording_state():
    from engine.runtime_bridge import handle_bridge_event
    from engine.voice_state_machine import get_voice_state_machine

    state_machine = get_voice_state_machine()
    state_machine.reset()
    with patch("eel.updateNexiState", create=True):
        handle_bridge_event({"type": "status", "status": "wake_detected", "source": "hotword"})
        handle_bridge_event({"type": "status", "status": "speech_started", "source": "hotword"})

    assert state_machine.get_state() == "recording_utterance"


def test_asr_result_preview_does_not_advance_vsm_before_thinking_ui():
    from engine.ui_state_manager import UIStateManager
    from engine.voice_state_machine import get_voice_state_machine

    state_machine = get_voice_state_machine()
    state_machine.reset()
    manager = UIStateManager(dedupe_ms=0)
    with patch("eel.updateNexiState", create=True):
        manager.emit("online", source="hotword", status="wake_detected")
        manager.emit("listening", source="hotword", status="listening_started")
        manager.emit("recognising", source="hotword", status="speech_started")
        manager.emit("recognising", source="hotword", status="asr_started")
        manager.emit("recognising", source="hotword", status="asr_result")
        state_during_preview = state_machine.get_state()
        manager.emit("thinking", source="hotword", status="thinking_started")

    assert state_during_preview == "recognizing"
    assert state_machine.get_state() == "thinking"
