import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_groq_intent_detects_essay_request_without_api(monkeypatch):
    from engine.groq_intent_planner import classify_intent
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("can you write an essay on solar system", source="hotword")
    assert result["route"] == "brain"
    assert result["intent"] == "general_qa"


def test_groq_intent_detects_workflow_switch():
    from engine.groq_intent_planner import classify_intent
    result = classify_intent(
        "can you write an essay on solar system",
        source="hotword",
        active_workflow={"name": "create_folder", "step": "ask_name"},
    )
    assert result["route"] == "workflow_switch"
    assert result["workflow_action"] == "switch"


def test_groq_intent_json_only_from_mocked_api(monkeypatch):
    from engine.groq_intent_planner import classify_intent
    monkeypatch.setenv("GROQ_API_KEY", "test")
    fake = Mock(status_code=200)
    fake.json.return_value = {"choices": [{"message": {"content": '{"route":"brain","intent":"essay_request","confidence":0.92,"reason":"essay","slots":{},"workflow_action":"none","expects_user_reply":false}'}}]}
    with patch("engine.groq_intent_planner.requests.post", return_value=fake):
        result = classify_intent("maybe something", source="typed")
    assert result["route"] == "brain"
    assert result["confidence"] == 0.92


def test_low_confidence_groq_result_falls_back_to_clarify(monkeypatch):
    from engine.groq_intent_planner import classify_intent
    monkeypatch.setenv("GROQ_API_KEY", "test")
    fake = Mock(status_code=200)
    fake.json.return_value = {"choices": [{"message": {"content": '{"route":"brain","intent":"unknown","confidence":0.2,"reason":"low","slots":{},"workflow_action":"none"}'}}]}
    with patch("engine.groq_intent_planner.requests.post", return_value=fake):
        result = classify_intent("ambiguous words", source="typed")
    assert result["route"] == "clarify"
