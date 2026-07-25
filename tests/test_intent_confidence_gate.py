import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_search_ronaldo_routes_to_search():
    # Search now goes through the live intelligence engine instead of opening a
    # browser URL. Mocked so the test stays offline/deterministic; the point of
    # the test is that "search ronaldo" is ROUTED to web search.
    from engine.local_skills import handle_local_skill
    with patch("engine.live_intelligence.live_web_search") as mock_search:
        mock_search.return_value = {"handled": True, "success": True,
                                    "message": "Live results for ronaldo"}
        result = handle_local_skill("search ronaldo")
    assert result.handled is True
    mock_search.assert_called_once()
    assert "ronaldo" in str(mock_search.call_args[0][0]).lower()


def test_low_confidence_local_action_blocked(monkeypatch):
    import engine.command as command
    fake_intent = Mock(name="intent")
    fake_intent.name = "open_app"
    monkeypatch.setenv("INTENT_LOCAL_ACTION_THRESHOLD", "0.75")
    with patch.object(command, "match_intent", return_value=(fake_intent, 0.39)):
        assert command.dispatch_intent("Sarıç") is False


def test_brain_failure_returns_safe_message_once(monkeypatch):
    monkeypatch.setitem(sys.modules, "pywhatkit", SimpleNamespace(playonyt=lambda *a, **k: None))
    from engine import features
    features._brain_fail_until = 0.0
    monkeypatch.setenv("BRAIN_FAIL_FAST_SECONDS", "60")
    safe = "I can't connect to my brain right now, but local actions are working."
    with patch.object(features, "ask_brain", return_value=safe) as mock_ask, patch.object(features, "speak") as mock_speak:
        assert features.chatBot("what is 2+2") == safe
        assert features.chatBot("what is 3+3") == safe
    assert mock_ask.call_count == 1
    assert mock_speak.call_count == 2
