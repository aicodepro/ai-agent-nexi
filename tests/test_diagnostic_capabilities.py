import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_diagnostic_capabilities_have_required_metadata():
    from engine.diagnostic_capabilities import check_diagnostic_capabilities

    capabilities = check_diagnostic_capabilities()
    keys = {item["key"] for item in capabilities}
    assert {
        "computer_use_harness",
        "browser_intelligence_layer",
        "human_approval_queue_v2",
        "tool_verifier_layer",
        "reflection_memory",
        "procedure_skill_library",
        "proactive_monitor",
        "conscious_hud",
    }.issubset(keys)
    for item in capabilities:
        assert item["role"]
        assert item["safety_policy"]
        assert item["verifier"]
        assert item["memory_rule"]
        assert item["diagnostic_output"]
        assert item["command"].startswith("check ")


def test_format_diagnostic_capabilities_single_layer():
    from engine.diagnostic_capabilities import format_diagnostic_capabilities

    text = format_diagnostic_capabilities("tool verifier layer")
    assert "Tool Verifier Layer" in text
    assert "Verifier:" in text
    assert "Memory:" in text


def test_phase3_bridge_routes_specific_capability_check():
    from engine.app.phase3_command_bridge import Phase3CommandBridge

    result = Phase3CommandBridge.try_handle("check tool verifier layer")
    assert result["handled"] is True
    check = result["result"]["data"]["check"]
    assert check["name"] == "Tool Verifier Layer"
    assert check["capability_key"] == "tool_verifier_layer"
