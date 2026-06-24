import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_groq_intent_detects_need_training(monkeypatch):
    from engine.groq_intent_planner import classify_intent

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("train Nexi for SEO", source="typed")
    assert result["route"] == "training"
    assert result["intent"] == "train_need_profile"


def test_groq_intent_detects_ultra_training(monkeypatch):
    from engine.groq_intent_planner import classify_intent

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = classify_intent("run training evaluation for sales", source="typed")
    assert result["route"] == "training"
    assert result["intent"] == "deep_training_command"
