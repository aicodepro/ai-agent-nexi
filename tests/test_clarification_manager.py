import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_clarification_sets_auto_listen():
    from engine import turn_manager
    from engine.clarification_manager import ask_clarification
    turn_manager.consume_auto_listen_request()
    response = ask_clarification("open", reason="clarification")
    assert response["expects_user_reply"] is True
    assert response["display_text"] == "Which app should I open?"
    assert turn_manager.should_auto_listen() is True
    turn_manager.consume_auto_listen_request()


def test_clarification_answer_received_logs(capsys):
    from engine.clarification_manager import ask_clarification, receive_answer
    ask_clarification("search", reason="clarification")
    result = receive_answer("AI agents")
    assert result["handled"] is True
    assert result["answer"] == "AI agents"
    assert "[CLARIFY] answer_received slot=query value=AI agents" in capsys.readouterr().out
