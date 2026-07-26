"""Router V3 semantic tier. Offline - no network, no provider.

Protects the properties that make an LLM-first router safe:
  - lifecycle/safety commands never depend on a model;
  - hallucinated capabilities can never execute;
  - a broken or empty model reply falls back instead of inventing a route;
  - retrieval survives misheard speech (the reason this router exists);
  - risk/approval come from the registry, never from the model.
"""
from __future__ import annotations

from unittest.mock import patch

from engine import router_semantic as rs

MANIFEST = [
    {"name": "take_screenshot", "aliases": ["screenshot"], "examples": ["take a screenshot"],
     "description": "capture the screen", "risk_level": "none", "requires_confirmation": False,
     "category": "desktop"},
    {"name": "open_app", "aliases": ["launch"], "examples": ["open chrome"],
     "description": "open an application", "risk_level": "low", "requires_confirmation": False,
     "category": "desktop"},
    {"name": "delete_file", "aliases": [], "examples": ["delete the file"],
     "description": "delete a file", "risk_level": "high", "requires_confirmation": True,
     "category": "files"},
]
NAMES = {c["name"] for c in MANIFEST}


# --- deterministic controls -------------------------------------------------

def test_lifecycle_commands_bypass_the_model():
    for phrase, expected in [("stop talking", "stop_speaking"), ("cancel", "cancel"),
                             ("emergency stop", "emergency_stop")]:
        matched = rs.match_lifecycle(phrase)
        assert matched is not None, phrase
        assert matched[1] == expected


def test_lifecycle_verb_inside_a_sentence_is_not_a_control():
    """'cancel my meeting' is a request, not the cancel control."""
    assert rs.match_lifecycle("cancel my meeting tomorrow") is None
    assert rs.match_lifecycle("stop the music at 5") is None


def test_approval_only_counts_when_awaiting_approval():
    assert rs.match_approval("yes", awaiting_approval=False) is None
    assert rs.match_approval("yes", awaiting_approval=True) == "approve"
    assert rs.match_approval("no", awaiting_approval=True) == "deny"


# --- retrieval --------------------------------------------------------------

def test_retrieval_survives_misheard_speech():
    got = [c["name"] for c in rs.retrieve_capabilities("tak a screen shot", MANIFEST, limit=2)]
    assert got[0] == "take_screenshot"
    got = [c["name"] for c in rs.retrieve_capabilities("opon krome", MANIFEST, limit=2)]
    assert got[0] == "open_app"


def test_retrieval_always_returns_candidates():
    got = rs.retrieve_capabilities("something entirely unrelated", MANIFEST, limit=3)
    assert len(got) == 3


# --- validation -------------------------------------------------------------

def test_hallucinated_capability_is_rejected():
    decision, error = rs.validate_decision({"capabilities": ["format_hard_drive"]}, NAMES)
    assert decision is None
    assert "hallucinated_capability" in error


def test_accepts_string_and_dict_capability_shapes():
    d1, _ = rs.validate_decision({"capabilities": ["open_app"], "confidence": 0.9}, NAMES)
    assert d1 is not None and d1.capabilities == ["open_app"]

    d2, _ = rs.validate_decision(
        {"capabilities": [{"name": "open_app", "arguments": {"app_name": "chrome"}}],
         "confidence": 0.9}, NAMES)
    assert d2 is not None
    assert d2.capabilities == ["open_app"]
    assert d2.arguments.get("app_name") == "chrome", "inline arguments must not be lost"


def test_empty_model_reply_is_treated_as_failure_not_clarification():
    """A contentless skeleton means the provider failed; asking the user to
    repeat themselves would be wrong."""
    assert rs._is_empty_decision({"capabilities": [], "user_goal": "",
                                  "missing_information": [], "confidence": 0.0})
    assert not rs._is_empty_decision({"capabilities": ["open_app"], "confidence": 0.8})
    assert not rs._is_empty_decision({"capabilities": [], "user_goal": "open my",
                                      "missing_information": ["app_name"], "confidence": 0.6})


# --- projection to the dispatcher contract ----------------------------------

def _by_name():
    return {c["name"]: c for c in MANIFEST}


def test_risk_and_confirmation_come_from_registry_not_model():
    """A model must not be able to talk its way out of an approval gate."""
    decision = rs.RouteDecision(capabilities=["delete_file"], confidence=0.9,
                                risk="low", approval_requirement="none")
    result = rs.decision_to_schema(decision, _by_name())
    assert result["risk_level"] == "high"
    assert result["requires_confirmation"] is True


def test_incomplete_request_becomes_clarification_without_executing():
    decision = rs.RouteDecision(request_status="incomplete", user_goal="open my",
                                missing_information=["app_name"], confidence=0.6)
    result = rs.decision_to_schema(decision, _by_name())
    assert result["route"] == "clarify"
    assert result["expects_user_reply"] is True
    assert "app_name" in result["missing_slots"]


def test_no_capability_match_goes_to_brain_not_a_tool():
    decision = rs.RouteDecision(capabilities=[], confidence=0.5, user_goal="what is gravity")
    result = rs.decision_to_schema(decision, _by_name())
    assert result["route"] == "brain"


# --- tier isolation ---------------------------------------------------------

def test_semantic_tier_returns_none_when_provider_unavailable():
    with patch("engine.providers.get_intent_provider", return_value=None):
        decided, trace = rs.semantic_route("open chrome")
    assert decided is None
    assert trace["ok"] is False
    assert trace["reason"] == "provider_unavailable"


def test_semantic_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("NEXI_ROUTER_V3_SEMANTIC", "false")
    assert rs.semantic_enabled() is False
    monkeypatch.setenv("NEXI_ROUTER_V3_SEMANTIC", "true")
    assert rs.semantic_enabled() is True
