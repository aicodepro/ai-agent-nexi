import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_groq_intent_detects_hand_gesture_control(monkeypatch):
    from engine.groq_intent_planner import classify_intent
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("enable hand mouse", source="typed")
    assert result["route"] == "local_skill"
    assert result["intent"] == "hand_gesture_control"
    assert result["slots"]["mode"] == "control"


def test_groq_intent_detects_eye_mouse_control(monkeypatch):
    from engine.groq_intent_planner import classify_intent
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("start eye mouse", source="typed")
    assert result["route"] == "local_skill"
    assert result["intent"] == "eye_mouse_control"


def test_groq_intent_detects_stop_camera_control(monkeypatch):
    from engine.groq_intent_planner import classify_intent
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("stop camera control", source="typed")
    assert result["intent"] == "stop_camera_control"
