import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _clean_all_state(monkeypatch):
    for env_key in ["GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_INTENT_API_KEY",
                     "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS"]:
        monkeypatch.delenv(env_key, raising=False)
    from engine import turn_manager, workflow_state
    from engine.followup_manager import clear_followup
    from engine.clarification_manager import clear_clarification
    workflow_state.clear_workflow()
    turn_manager.consume_auto_listen_request()
    clear_followup("test_setup")
    clear_clarification("test_setup")
    yield
    workflow_state.clear_workflow()
    turn_manager.consume_auto_listen_request()
    clear_followup("test_teardown")
    clear_clarification("test_teardown")


def test_low_confidence_does_not_go_idle():
    from engine import turn_manager
    from engine.clarification_manager import ask_clarification
    turn_manager.consume_auto_listen_request()
    response = ask_clarification("um", reason="clarification")
    assert response["ui_state_after"] == "listening"
    assert turn_manager.should_auto_listen() is True
    turn_manager.consume_auto_listen_request()


def test_open_command_asks_specific_question():
    import engine.command as command
    from engine import turn_manager
    with patch("engine.command.speak") as mock_speak, patch("engine.command.safe_eel_call"):
        command.allCommands("open")
    mock_speak.assert_any_call("Which app should I open?")
    assert turn_manager.should_auto_listen() is True
    turn_manager.consume_auto_listen_request()
