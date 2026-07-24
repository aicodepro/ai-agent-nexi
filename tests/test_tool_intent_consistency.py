"""Executable tool names are derived from the registry into the intent taxonomy.

These tests guard schema survival, non-brain routing, and future registry additions.
"""
import os
import sys
import importlib
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import intent_taxonomy as tax
from engine.router.decision import route_for_intent
from engine.tool_registry import _TOOLS

# Intents that are deliberately NOT tool-routed. `sleep`/`wake`/`stop_speaking`/
# `cancel` are lifecycle ROUTES handled by engine.intent_pre_router before the tool
# layer ever runs, so route_for_intent() sending them to "brain" is never reached.
# Anything added here needs a reason, not just a green suite.
_NOT_TOOL_ROUTED = {
    "sleep": "lifecycle route handled by intent_pre_router",
    "wake": "lifecycle route handled by intent_pre_router",
    "stop_speaking": "interrupt route handled by intent_pre_router",
    "cancel": "cancel route handled by intent_pre_router",
}

_ENABLED = sorted(name for name, spec in _TOOLS.items() if spec.enabled)


@pytest.mark.parametrize("name", _ENABLED)
def test_enabled_tool_survives_schema_validation(name):
    """empty_result()/exact_schema() must not scrub the intent to 'unknown'."""
    if name in _NOT_TOOL_ROUTED:
        pytest.skip(_NOT_TOOL_ROUTED[name])
    assert name in tax.ALLOWED_INTENTS, (
        f"{name!r} is an enabled tool but is missing from intent_taxonomy.ALLOWED_INTENTS, "
        f"so empty_result()/exact_schema() will silently rewrite its intent to 'unknown'."
    )
    result = tax.empty_result(route="tool", intent=name, domain="system", confidence=0.9)
    assert result["intent"] == name, f"{name!r} was scrubbed to {result['intent']!r}"


@pytest.mark.parametrize("name", _ENABLED)
def test_enabled_tool_routes_to_a_tool_not_chat(name):
    """route_for_intent() must not silently divert an executable tool to the brain."""
    if name in _NOT_TOOL_ROUTED:
        pytest.skip(_NOT_TOOL_ROUTED[name])
    route = route_for_intent(name)
    assert route in {"tool", "output", "workflow", "memory", "system"}, (
        f"{name!r} is an enabled tool but route_for_intent() returns {route!r} — it will be "
        f"answered by chat instead of executed. Add it to intent_taxonomy.TOOL_INTENTS "
        f"(or OUTPUT_INTENTS)."
    )


def test_no_intent_claims_to_be_both_tool_and_brain():
    overlap = tax.TOOL_INTENTS & tax.BRAIN_INTENTS
    assert not overlap, f"intents in both TOOL_INTENTS and BRAIN_INTENTS: {sorted(overlap)}"


def test_tool_intents_are_all_allowed():
    """Anything in TOOL_INTENTS must survive schema validation."""
    missing = sorted(tax.TOOL_INTENTS - tax.ALLOWED_INTENTS)
    assert not missing, f"in TOOL_INTENTS but not ALLOWED_INTENTS (will scrub to 'unknown'): {missing}"


def test_which_model_regression():
    """Direct regression for the bug this guard was written after."""
    assert "which_model" in _TOOLS
    assert "which_model" in tax.ALLOWED_INTENTS
    assert route_for_intent("which_model") == "tool"


def test_taxonomy_derives_new_executable_tool_capabilities():
    name = "test_dynamic_capability"
    _TOOLS[name] = replace(next(iter(_TOOLS.values())), name=name, enabled=True)
    planner = importlib.import_module("engine.groq_intent_planner")
    try:
        importlib.reload(tax)
        importlib.reload(planner)
        assert name in tax.ALLOWED_INTENTS
        assert name in tax.TOOL_INTENTS
        assert planner._normalize({"route": "local_skill", "intent": name})["intent"] == name
    finally:
        _TOOLS.pop(name, None)
        importlib.reload(tax)
        importlib.reload(planner)
