import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _clean_all_state(monkeypatch):
    for env_key in ["GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_INTENT_API_KEY",
                     "JARVIS_ENABLE_LEGACY_BRAIN_PROVIDERS"]:
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


def test_auto_listen_requested_after_missing_slot_question():
    import engine.command as command
    from engine import turn_manager
    with patch("engine.command.speak") as mock_speak, patch("engine.command.safe_eel_call"):
        command.allCommands("create a folder")
    mock_speak.assert_any_call("What should I name the folder?", handler_reason="missing_slot")
    assert turn_manager.should_auto_listen() is True


def test_hotword_missing_slot_starts_auto_followup_capture():
    from engine import turn_manager
    from engine.command_bus import dispatch_unified_command
    with patch("engine.command.speak"), \
         patch("engine.command.safe_eel_call"), \
         patch("engine.command.takecommand", return_value="") as mock_take:
        dispatch_unified_command("create a folder", source="hotword")
    mock_take.assert_called_once()
    assert turn_manager.should_auto_listen() is False


def test_active_workflow_accepts_folder_name_answer():
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, cancel_workflow
    cancel_workflow("test")
    start_workflow("create_folder", "create a folder", "typed")
    result = handle_workflow_turn("Demo Website", "typed")
    assert result["handled"] is True
    assert "Where should I create" in result["response"]
    cancel_workflow("test")


def test_active_workflow_switches_to_local_skill_on_open_chrome():
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, cancel_workflow
    cancel_workflow("test")
    start_workflow("create_folder", "create a folder", "typed")
    result = handle_workflow_turn("open chrome", "typed")
    assert result["switch"] is True
    assert result["planner"]["route"] == "workflow_switch"
    cancel_workflow("test")


def test_workflow_switch_logs_real_brain_target(capsys):
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, cancel_workflow
    cancel_workflow("test")
    start_workflow("create_folder", "create a folder", "typed")
    handle_workflow_turn("can you write an essay about solar system", "typed")
    out = capsys.readouterr().out
    assert "[WORKFLOW] switch_detected from=create_folder to=brain" in out
    cancel_workflow("test")


def test_repeat_last_response():
    from engine.conversation_context import clear_recent_context, add_assistant_turn, get_last_assistant_response
    clear_recent_context()
    add_assistant_turn("Previous answer")
    last = get_last_assistant_response()
    assert last == "Previous answer"


def test_repeat_last_logs_found(capsys):
    from engine.conversation_context import clear_recent_context, add_assistant_turn, find_recent_reference
    clear_recent_context()
    add_assistant_turn("Previous answer")
    ref = find_recent_reference("it")
    assert ref is not None
    assert ref.get("reference_type") == "latest_assistant_output"
