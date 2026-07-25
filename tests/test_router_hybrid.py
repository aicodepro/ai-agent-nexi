"""Hybrid front-door tests: the tiered Master Router is primary for compound and
fuzzy language; the legacy table is the fallback when it is not confident.

The Master Router is faked where its decision matters so these tests are
deterministic and independent of the embedder that happens to be installed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.groq_intent_router_v2 import _deterministic_is_confident, route_intent_v2
from engine.intent_taxonomy import empty_result
from engine.router.decision import Decision


def _ctx(**overrides):
    base = {
        "source": "test",
        "pending_clarification": {},
        "pending_followup": {},
        "active_workflow": {},
        "active_training": {},
        "latest_output": {"available": False},
        "recent_turns": [],
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _no_real_correction_file_reads(monkeypatch):
    import engine.correction_learner as learner
    monkeypatch.setattr(learner, "apply_correction", lambda _text: {"matched": False})


# ── compound / multi-step -> react (deterministic, no LLM) ──────────────────────
@pytest.mark.parametrize("text", [
    "open notepad and type hello world",
    "take a screenshot and save it to the desktop",
    "mute the music and pause the video",
    "open chrome and then search for cats",
    "find my note about project X and then save it",
])
def test_compound_commands_route_to_react_without_llm(monkeypatch, text):
    import engine.groq_intent_router_v2 as router
    monkeypatch.setattr(router, "_route_with_groq", lambda *_a, **_k: pytest.fail("LLM should not run"))
    monkeypatch.setattr(router, "_route_with_master", lambda *_a, **_k: pytest.fail("master should not run for compound"))
    result = route_intent_v2(text, source="typed", context=_ctx())
    assert result["route"] == "react"
    assert result["intent"] == "react_multi_step"
    assert result["should_call_tool"] is False


# ── general_qa is a soft guess -> must reach the smart middle, not short-circuit ─
def test_general_qa_is_not_treated_as_confident():
    assert _deterministic_is_confident({"route": "brain", "intent": "general_qa", "confidence": 0.86}) is False
    # social/identity brain replies stay authoritative
    assert _deterministic_is_confident({"route": "brain", "intent": "social_close", "confidence": 0.97}) is True


# ── the tiered router takes the wheel on a confident action ─────────────────────
def test_hybrid_uses_confident_master_action(monkeypatch):
    import engine.router as router_pkg
    decision = Decision(
        result=empty_result(route="tool", intent="get_battery_status", domain="system", confidence=0.5),
        band="act", tier=0, sim=0.75,
    )
    monkeypatch.setattr(router_pkg, "route", lambda text, ctx=None: decision)
    # the router is only consulted once WARM — cold, the turn must not block on the
    # ~83s embedder build (see test_master_router_is_never_built_in_the_voice_turn)
    monkeypatch.setattr(router_pkg, "_ROUTER", object(), raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = route_intent_v2("hey can you show me the battery please", source="typed", context=_ctx())
    assert result["route"] == "tool"
    assert result["intent"] == "get_battery_status"


# ── a weak semantic match must NOT override the legacy fallback ──────────────────
def test_master_router_is_never_built_inside_a_voice_turn(monkeypatch):
    """REGRESSION: _route_with_master used to call engine.router.route() directly,
    which lazily builds the e5 embedder — ~83s, over the network — INSIDE the turn.
    It ran in the Eel/UI process, so it froze the UI and left NEXI saying
    "thinking..." until the session timed out. A cold router must be skipped (and
    warmed in the background), never built inline."""
    import engine.groq_intent_router_v2 as router
    import engine.router as router_pkg

    monkeypatch.setattr(router_pkg, "_ROUTER", None, raising=False)  # cold
    monkeypatch.setattr(router_pkg, "get_router", lambda: pytest.fail("built the router inside the turn"))
    monkeypatch.setattr(router_pkg, "route", lambda *_a, **_k: pytest.fail("routed via a cold master"))
    monkeypatch.setattr(router, "_warm_master_router", lambda: None)  # don't spawn a real build
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = route_intent_v2("hey can you show me the battery please", source="typed", context=_ctx())
    # answered by the legacy path instead of hanging
    assert result["route"] in {"brain", "clarify", "tool"}


def test_cold_master_triggers_a_background_warm(monkeypatch):
    import engine.groq_intent_router_v2 as router
    import engine.router as router_pkg

    warmed = {"n": 0}
    monkeypatch.setattr(router_pkg, "_ROUTER", None, raising=False)
    monkeypatch.setattr(router, "_warm_master_router", lambda: warmed.__setitem__("n", warmed["n"] + 1))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    route_intent_v2("hey can you show me the battery please", source="typed", context=_ctx())
    assert warmed["n"] >= 1, "a cold master must kick off a background warm"


def test_hybrid_ignores_weak_master_match(monkeypatch):
    import engine.router as router_pkg
    decision = Decision(
        result=empty_result(route="tool", intent="screen_read", domain="desktop", confidence=0.5),
        band="act", tier=0, sim=0.50,  # below the 0.62 floor
    )
    monkeypatch.setattr(router_pkg, "route", lambda text, ctx=None: decision)
    monkeypatch.setattr(router_pkg, "_ROUTER", object(), raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = route_intent_v2("make my screen brighter", source="typed", context=_ctx())
    assert result["route"] == "clarify"


# ── the model/semantic layer can never mint approval or workflow-control authority
def test_master_cannot_mint_forbidden_intents(monkeypatch):
    import engine.router as router_pkg
    decision = Decision(
        result=empty_result(route="tool", intent="approve_action", domain="system", confidence=0.5),
        band="act", tier=0, sim=0.99,
    )
    monkeypatch.setattr(router_pkg, "route", lambda text, ctx=None: decision)
    # must be WARM, or the warm-gate skips the master and this asserts nothing
    monkeypatch.setattr(router_pkg, "_ROUTER", object(), raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = route_intent_v2("go ahead and do the approval", source="typed", context=_ctx())
    assert result["intent"] != "approve_action"


# ── hybrid can be disabled -> master is never consulted ─────────────────────────
def test_hybrid_can_be_disabled(monkeypatch):
    import engine.router as router_pkg
    monkeypatch.setenv("NEXI_ROUTER_HYBRID", "0")
    monkeypatch.setattr(router_pkg, "route", lambda *_a, **_k: pytest.fail("master must not run when hybrid is off"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = route_intent_v2("make my screen brighter", source="typed", context=_ctx())
    assert result["route"] == "clarify"
