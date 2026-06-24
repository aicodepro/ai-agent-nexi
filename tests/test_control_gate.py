import pytest
from control.gate import (
    RISK_POLICY, engage_emergency_stop, clear_emergency_stop,
    is_emergency_stopped, ActionGate, dispatch_action,
)


def setup_function():
    clear_emergency_stop()


def test_risk_policy_structure():
    assert "safe" in RISK_POLICY
    assert "medium" in RISK_POLICY
    assert "high" in RISK_POLICY
    assert "critical" in RISK_POLICY
    for key, policy in RISK_POLICY.items():
        assert "allowed" in policy
        assert "confirm" in policy


def test_emergency_stop():
    assert is_emergency_stopped() is False
    engage_emergency_stop()
    assert is_emergency_stopped() is True
    clear_emergency_stop()
    assert is_emergency_stopped() is False


def test_gate_blocks_unknown():
    gate = ActionGate()
    result = gate.execute("nonexistent_action_xyz")
    assert result.get("ok") is False
    assert "Unknown" in result.get("message", "")


def test_dispatch_unknown():
    result = dispatch_action("nonexistent_action_xyz")
    assert result.get("ok") is False


def test_emergency_stop_blocks_action():
    engage_emergency_stop()
    gate = ActionGate()
    result = gate.execute("open_app")
    assert result.get("ok") is False
    assert "Emergency stop" in result.get("message", "")
    clear_emergency_stop()


def test_risk_policy_safe_defaults():
    policy = RISK_POLICY["safe"]
    assert policy["allowed"] is True
    assert policy["confirm"] is False


def test_risk_policy_critical():
    policy = RISK_POLICY["critical"]
    assert policy["allowed"] is False
