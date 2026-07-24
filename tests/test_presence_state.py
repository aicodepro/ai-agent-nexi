import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_presence_state_updates_from_ui_state():
    from engine.presence_state import get_presence, reset_presence_state

    reset_presence_state()
    presence = get_presence()
    presence.update_from_ui_state("thinking", text="open chrome", status="command_started", session_id="abc")

    data = presence.to_dict()
    assert data["mode"] == "thinking"
    assert data["attention"] == "tool"
    assert data["last_event"] == "command_started"
    assert data["session_id"] == "abc"
    assert "open chrome" in data["current_goal"]


def test_ui_state_payload_includes_presence():
    from engine.presence_state import reset_presence_state
    from engine.ui_state_manager import emit_state, get_ui_state_manager

    reset_presence_state()
    get_ui_state_manager().reset()

    with patch("eel.updateNexiState", create=True) as update:
        emit_state("saying", source="tts", status="speaking_started", session_id="sid1", force=True)

    payload = update.call_args[0][0]
    assert payload["state"] == "saying"
    assert payload["presence"]["mode"] == "speaking"
    assert payload["presence"]["attention"] == "user"
    assert payload["presence"]["last_event"] == "speaking_started"


def test_presence_state_helpers_clamp_confidence_and_format_ui_string():
    from engine.presence_state import get_presence, reset_presence_state

    reset_presence_state()
    presence = get_presence()
    presence.update_confidence(2.5)
    presence.update_attention("audio")
    presence.set_goal("waiting for user command")

    data = presence.to_dict()
    assert data["confidence"] == 1.0
    ui = presence.to_ui_string()
    assert "ATTENTION: AUDIO" in ui
    assert "CONFIDENCE: 100%" in ui
