"""NEXI understands a build request in the LIVE router — no magic phrase.

Darsh: "I will not issue 'studio mode'. Nexi should interpret the request through its
own self-understanding... if needed add an LLM that works like deepseek v4 flash."

Architecture pinned here:
  * deterministic scorer FIRST — free, instant, cannot hallucinate a build request;
  * the LLM tier is consulted ONLY for the ambiguous middle (0.15-0.70), so a clear yes
    or clear no never costs a model call on the voice path;
  * an inferred request routes to CLARIFY, never straight to a build. The confirming
    reply is the CEO turn that mints the authorization token, so a guess can never
    authorize an 11-stage build.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.studio import intent_detect as det


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Default the deterministic path so tests never hit the network."""
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "0")


# ---- the LLM tier ----------------------------------------------------------------

def test_llm_is_not_called_for_a_clear_non_build(monkeypatch):
    """A clear 'no' must never cost a model call on the voice path."""
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "1")

    def _boom(*a, **k):
        raise AssertionError("LLM consulted for an obvious non-build")

    out = det.detect_smart("open chrome", generate_fn=_boom)
    assert out["action"] == "ignore"


def test_llm_is_not_called_for_an_explicit_trigger(monkeypatch):
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "1")

    def _boom(*a, **k):
        raise AssertionError("LLM consulted for an explicit trigger")

    out = det.detect_smart("let's build a dashboard", generate_fn=_boom)
    assert out["action"] == "build" and out["explicit"]


def test_llm_rescues_an_indirect_request(monkeypatch):
    """The whole point of the tier: phrasing no keyword list would catch."""
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "1")
    called = []

    def _fake(prompt):
        called.append(prompt)
        return '{"is_build": true, "goal": "automate the CSV export", "confidence": 0.9}'

    out = det.detect_smart("the CSV thing is manual, sort it out for me", generate_fn=_fake)
    assert called, "ambiguous utterance should have reached the LLM"
    assert out["action"] == "confirm"
    assert "CSV" in out["goal"]
    assert out.get("llm_consulted") is True


def test_llm_can_veto_a_weak_keyword_hit(monkeypatch):
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "1")
    out = det.detect_smart(
        "I need a break from this project",
        generate_fn=lambda p: '{"is_build": false, "goal": "", "confidence": 0.9}')
    assert out["action"] == "ignore"


def test_llm_failure_falls_back_to_deterministic(monkeypatch):
    """Offline / provider down must degrade, never break the turn."""
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "1")

    def _boom(prompt):
        raise RuntimeError("provider down")

    out = det.detect_smart("the CSV thing is manual, sort it out for me", generate_fn=_boom)
    assert out["action"] in {"ignore", "confirm"}      # a verdict, not an exception


def test_llm_garbage_output_is_ignored(monkeypatch):
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "1")
    out = det.detect_smart("something vague about files",
                           generate_fn=lambda p: "not json at all")
    assert "action" in out


def test_llm_tier_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NEXI_INTENT_DETECT_LLM", "0")

    def _boom(*a, **k):
        raise AssertionError("LLM called while disabled")

    det.detect_smart("the CSV thing is manual, sort it out", generate_fn=_boom)


# ---- live router wiring ----------------------------------------------------------

def _route(text):
    import io, contextlib
    from engine.groq_intent_router_v2 import route_intent_v2
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return route_intent_v2(text, source="test")


@pytest.mark.parametrize("text", [
    "I want a python function that reverses a string",
    "can you make me a tool that renames files",
])
def test_inferred_build_reaches_the_router(text):
    out = _route(text)
    assert out["intent"] == "nexi_start_studio_build"
    assert out["route"] == "clarify", "an inferred build must be confirmed, never auto-started"
    assert out.get("clarification_question"), "NEXI must actually ask before committing"
    assert out.get("expects_user_reply") is True
    assert out["slots"]["goal"], "the goal must be carried into the confirmation"


def test_inferred_build_does_not_mint_authorization():
    """The safety line: a guess must never carry a Studio auth token."""
    out = _route("I want a python function that reverses a string")
    assert "_studio_auth" not in (out.get("slots") or {}), (
        "an inferred request must not self-authorize — the CEO's confirming reply does")


@pytest.mark.parametrize("text,intent", [
    ("open chrome", "open_app"),
    ("what time is it", "tell_time"),
])
def test_routine_commands_are_untouched(text, intent):
    assert _route(text)["intent"] == intent


def test_question_about_building_still_goes_to_the_brain():
    out = _route("how do I build a react app")
    assert out["intent"] != "nexi_start_studio_build"


def test_inference_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("NEXI_INFER_BUILD_INTENT", "0")
    out = _route("I want a python function that reverses a string")
    assert out["intent"] != "nexi_start_studio_build"
