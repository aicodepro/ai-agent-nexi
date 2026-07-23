import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _enable_safety_gate(monkeypatch):
    """conftest defaults SAFETY_GATE_ENABLED=false for the suite (the gate is a live
    network classifier). This file tests the gate itself, so turn it on."""
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "true")




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
