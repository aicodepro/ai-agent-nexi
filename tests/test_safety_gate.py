import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_safety_gate_triggers_on_risky_actions():
    from engine.safety_gate import should_safety_check
    assert should_safety_check("delete the project folder") is True
    assert should_safety_check("run terminal command dir") is True


def test_safety_gate_does_not_trigger_on_open_chrome():
    from engine.safety_gate import should_safety_check
    assert should_safety_check("open chrome") is False


def test_safety_gate_fallback_requires_confirmation_without_key(monkeypatch):
    from engine.safety_gate import classify_safety
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    decision = classify_safety("delete notes")
    assert decision["allowed"] is True
    assert decision["requires_confirmation"] is True
    assert decision["risk"] == "medium"
