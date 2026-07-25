import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _clear_pending_state():
    from engine.clarification_manager import clear_clarification
    from engine.followup_manager import clear_followup
    from engine.workflow_state import clear_workflow
    from engine.turn_manager import consume_auto_listen_request

    clear_clarification("test")
    clear_followup("test")
    clear_workflow()
    consume_auto_listen_request()
    yield
    clear_clarification("test")
    clear_followup("test")
    clear_workflow()
    consume_auto_listen_request()


def test_open_then_chrome_executes_open_app(capsys):
    from engine.command_bus import submit_user_command

    with patch("engine.command.speak"), patch("engine.command.safe_eel_call"), \
         patch("engine.tool_result_verifier._app_process_running", return_value=True), \
         patch("engine.local_skills.subprocess.Popen") as mock_popen:
        submit_user_command("open", source="typed", mode="typed")
        submit_user_command("chrome", source="typed", mode="typed")

    mock_popen.assert_called()
    out = capsys.readouterr().out
    assert "[CLARIFY] answer_received slot=app_name value=chrome" in out
    assert "[TOOL] executing name=open_app" in out
    assert "[TOOL] success name=open_app" in out


def test_open_then_youtube_executes_open_website(capsys):
    from engine.command_bus import submit_user_command

    with patch("engine.command.speak"), patch("engine.command.safe_eel_call"), patch("engine.local_skills.webbrowser.open") as mock_open:
        submit_user_command("open", source="typed", mode="typed")
        submit_user_command("youtube", source="typed", mode="typed")

    mock_open.assert_called_once()
    assert "youtube" in mock_open.call_args.args[0]
    out = capsys.readouterr().out
    assert "[TOOL] executing name=open_website" in out
    assert "[TOOL] success name=open_website" in out


def test_search_then_ronaldo_executes_search():
    from engine.command_bus import submit_user_command

    # search now runs through the live intelligence engine, not a browser open;
    # the point of this test is that the "ronaldo" answer fills the pending slot.
    with patch("engine.command.speak"), patch("engine.command.safe_eel_call"), \
         patch("engine.live_intelligence.live_web_search") as mock_search:
        mock_search.return_value = {"handled": True, "success": True, "message": "Live results"}
        submit_user_command("search", source="typed", mode="typed")
        submit_user_command("ronaldo", source="typed", mode="typed")

    mock_search.assert_called_once()
    assert "ronaldo" in str(mock_search.call_args[0][0]).lower()


def test_pending_clarification_allows_single_word_answer(capsys):
    from engine.command_bus import submit_user_command

    with patch("engine.command.speak"), patch("engine.command.safe_eel_call"), patch("engine.local_skills.subprocess.Popen"):
        submit_user_command("open", source="hotword", mode="voice")
        submit_user_command("chrome", source="hotword", mode="voice")

    assert "[TRANSCRIPT] accepted reason=pending_followup_short_answer" in capsys.readouterr().out


def test_create_file_then_filename_continues_workflow():
    from engine.local_skills import handle_local_skill, continue_workflow
    from engine.workflow_state import get_workflow, clear_workflow, has_active_workflow

    clear_workflow()
    handle_local_skill("create file")
    assert has_active_workflow() is True
    wf = get_workflow()
    assert wf["name"] == "local_create_file"
    assert wf["step"] == "ask_name"
    msg = continue_workflow("notes")
    assert "Where" in msg
    wf2 = get_workflow()
    assert wf2["step"] == "ask_location"
    assert wf2["slots"]["file_name"] == "notes"
    clear_workflow()
