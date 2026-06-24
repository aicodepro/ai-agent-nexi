import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_intent_open_requires_clarification(monkeypatch):
    from engine.groq_intent_planner import classify_intent

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("open", source="typed")
    assert result["route"] == "clarify"
    assert result["intent"] == "open_app"
    assert result["expects_user_reply"] is True
    assert result["clarification_question"] == "Which app should I open?"


def test_intent_open_chrome_pending_executes_open_app(monkeypatch):
    from engine.groq_intent_planner import classify_intent

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("chrome", source="hotword", pending_followup={"followup_type": "open_app"})
    assert result["route"] == "local_skill"
    assert result["intent"] == "open_app"
    assert result["slots"]["app_name"] == "chrome"


def test_intent_open_youtube_pending_executes_open_website(monkeypatch):
    from engine.groq_intent_planner import classify_intent

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("youtube", source="hotword", pending_followup={"followup_type": "open_app"})
    assert result["route"] == "local_skill"
    assert result["intent"] == "open_website"
    assert result["slots"]["url"] == "youtube.com"


def test_low_confidence_never_idle(monkeypatch):
    from engine.groq_intent_planner import classify_intent

    monkeypatch.setenv("GROQ_API_KEY", "test")
    fake = Mock(status_code=200)
    fake.json.return_value = {"choices": [{"message": {"content": '{"route":"brain","intent":"unknown","confidence":0.2,"reason":"low","slots":{}}'}}]}
    with patch("engine.groq_intent_planner.requests.post", return_value=fake):
        result = classify_intent("ambiguous words", source="typed")
    assert result["route"] == "clarify"
    assert result["route"] != "idle"
