import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_component_status_to_dict():
    from engine.diagnostics import ComponentStatus

    data = ComponentStatus("Brain", "ready", "ok", last_check=1.0, latency_ms=2).to_dict()
    assert data["name"] == "Brain"
    assert data["status"] == "ready"
    assert data["latency_ms"] == 2


def test_check_all_contains_expected_components():
    from engine.diagnostics import Diagnostics

    health = Diagnostics.check_all(force=True)
    assert {"microphone", "hotword", "clap", "asr", "brain", "tts", "memory", "tools"}.issubset(health)
    assert {"computer_use_harness", "tool_verifier_layer", "reflection_memory", "conscious_hud"}.issubset(health)
    assert all(item.last_check > 0 for item in health.values())


def test_diagnostic_capability_status_includes_policy_metadata():
    from engine.diagnostics import Diagnostics

    health = Diagnostics.check_all(force=True)
    item = health["tool_verifier_layer"]
    assert item.role
    assert item.safety_policy
    assert item.verifier
    assert item.memory_rule


def test_check_asr_disabled_without_groq_key(monkeypatch):
    from engine.diagnostics import Diagnostics

    monkeypatch.setenv("ASR_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = Diagnostics.check_asr()
    assert result.status == "disabled"
    assert "Groq key" in result.detail


def test_check_tools_reports_registered_count():
    from engine.diagnostics import Diagnostics

    result = Diagnostics.check_tools()
    assert result.status == "ready"
    assert "registered" in result.detail


def test_check_all_dict_is_json_safe():
    import json
    from engine.diagnostics import check_all_dict

    payload = check_all_dict(force=True)
    json.dumps(payload)
    assert payload["tools"]["status"] in {"ready", "error"}


def test_get_uptime_returns_string():
    from engine.diagnostics import Diagnostics

    assert Diagnostics.get_uptime().endswith("s")
