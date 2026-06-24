import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _clear_pending_state(monkeypatch):
    for env_key in ["GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_INTENT_API_KEY",
                     "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS"]:
        monkeypatch.delenv(env_key, raising=False)
    from engine.clarification_manager import clear_clarification
    from engine.followup_manager import clear_followup
    from engine.turn_manager import consume_auto_listen_request
    from engine import workflow_state

    workflow_state.clear_workflow()
    clear_clarification("test")
    clear_followup("test")
    consume_auto_listen_request()
    yield
    workflow_state.clear_workflow()
    clear_clarification("test")
    clear_followup("test")
    consume_auto_listen_request()


def test_unclear_intent_asks_again_and_requests_auto_listen():
    import engine.command as command
    from engine.clarification_manager import has_pending_clarification
    from engine.turn_manager import should_auto_listen

    with patch("engine.command.speak"), patch("engine.command.safe_eel_call"):
        command.allCommands("zzzz")

    assert has_pending_clarification() is True
    assert should_auto_listen() is True


def test_no_idle_clarification_logs(capsys):
    import engine.command as command

    with patch("engine.command.speak"), patch("engine.command.safe_eel_call"):
        command.allCommands("zzzz")

    out = capsys.readouterr().out
    assert "[CLARIFY] pending=true" in out
    assert "[TURN] auto_listen requested reason=clarification" in out
