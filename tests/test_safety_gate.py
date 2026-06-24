import pytest
from intent.safety_gate import should_safety_check, classify_safety, enforce_safety


def test_should_safety_check_risky(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    assert should_safety_check("delete my file") is True
    assert should_safety_check("open terminal") is True
    assert should_safety_check("run code") is True


def test_should_safety_check_safe(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    assert should_safety_check("hello there") is False
    assert should_safety_check("what time is it") is False
    assert should_safety_check("open chrome") is False


def test_should_safety_check_disabled(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", False)
    assert should_safety_check("delete my file") is False


def test_classify_safety_low(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    result = classify_safety("hello, how are you?")
    assert result["risk"] == "low"
    assert result["requires_confirmation"] is False


def test_classify_safety_medium(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    result = classify_safety("delete my download folder")
    assert result["risk"] == "medium"
    assert result["requires_confirmation"] is True


def test_classify_safety_high(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    result = classify_safety("shutdown the computer")
    assert result["risk"] == "high"
    assert result["requires_confirmation"] is True


def test_classify_safety_format_disk(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    result = classify_safety("format disk c")
    assert result["risk"] == "high"


def test_classify_safety_rm_rf(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    result = classify_safety("rm -rf /")
    assert result["risk"] == "high"


def test_classify_safety_password(monkeypatch):
    monkeypatch.setattr("intent.safety_gate.cfg.safety_gate_enabled", True)
    result = classify_safety("my password is secret123")
    assert result["risk"] == "medium"


def test_enforce_safety_low():
    decision = enforce_safety({"risk": "low"})
    assert decision["allowed"] is True
    assert decision["requires_confirmation"] is False


def test_enforce_safety_medium():
    decision = enforce_safety({"risk": "medium"})
    assert decision["allowed"] is True
    assert decision["requires_confirmation"] is True


def test_enforce_safety_high():
    decision = enforce_safety({"risk": "high"})
    assert decision["allowed"] is False
    assert decision["requires_confirmation"] is True
