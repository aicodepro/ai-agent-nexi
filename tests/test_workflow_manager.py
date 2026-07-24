import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _clear_workflow(monkeypatch):
    for env_key in ["GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_INTENT_API_KEY",
                     "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS"]:
        monkeypatch.delenv(env_key, raising=False)
    from engine.workflow_state import clear_workflow
    from engine.followup_manager import clear_followup
    from engine.clarification_manager import clear_clarification
    from engine import turn_manager
    clear_workflow()
    clear_followup("test_cleanup")
    clear_clarification("test_cleanup")
    turn_manager.consume_auto_listen_request()
    yield
    clear_workflow()
    clear_followup("test_cleanup")
    clear_clarification("test_cleanup")
    turn_manager.consume_auto_listen_request()


def test_active_workflow_beats_brain(tmp_path, monkeypatch):
    import engine.command as command
    from engine.workflow_state import start_workflow

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    start_workflow("local_note", "ask_text", {})
    with patch.object(command, "route_intent") as mock_route, \
         patch.object(command, "speak") as mock_speak, \
         patch.object(command, "eel"):
        command.allCommands("remember this")
    mock_route.assert_not_called()
    mock_speak.assert_called_once_with("Note saved.", handler_reason="missing_slot")


def test_cancel_clears_workflow():
    from engine import workflow_state
    from engine.workflow_manager import handle_active_workflow

    workflow_state.start_workflow("local_web_search", "ask_query", {})
    assert handle_active_workflow("cancel") == "Cancelled."
    assert workflow_state.has_active_workflow() is False


def test_local_skill_beats_brain():
    import engine.command as command

    with patch.object(command, "route_intent") as mock_route, \
         patch.object(command, "speak") as mock_speak, \
         patch.object(command, "eel"):
        command.allCommands("open app")
    mock_route.assert_not_called()
    mock_speak.assert_called_once_with("Opening app.", handler_reason="tool")


def test_workflow_snapshot_cannot_mutate_live_state():
    from engine import workflow_state

    workflow_state.start_workflow("create_folder", "ask_name", {"location": "Desktop"})
    snapshot = workflow_state.get_workflow()
    snapshot["step"] = "tampered"
    snapshot["slots"]["location"] = "outside"

    current = workflow_state.get_workflow()
    assert current["step"] == "ask_name"
    assert current["slots"]["location"] == "Desktop"
