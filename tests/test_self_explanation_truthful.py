"""Nexi must explain the route she ACTUALLY took.

engine.realtime_cognitive_engine computes a strategy on every command, but
engine.groq_intent_router_v2 is what really dispatches — they are independent and
regularly disagree. Self-explanation used to read the strategy, so Nexi
confidently narrated decisions she never made (ran get_battery_status, said
"general_qa via brain"). That is confabulation, not explanation.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine import cognitive_context, intent_explainer


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    # a truly empty explainer — record_intent_decision({}) would still count as history
    monkeypatch.setattr(intent_explainer, "_last_explanation", {})
    cognitive_context.set_last_strategy({})
    yield
    cognitive_context.set_last_strategy({})


def _disagree():
    """The real router ran the battery tool; the parallel strategy thinks chat."""
    intent_explainer.record_intent_decision(
        {"route": "tool", "intent": "get_battery_status", "confidence": 0.95, "reason": "tier0:medium"},
        selected_tool="get_battery_status",
    )
    cognitive_context.set_last_strategy({
        "normalized_text": "what is my battery",
        "chosen_route": "brain",
        "chosen_intent": "general_qa",
        "confidence": 0.86,
        "reason": "qa_prefix='what is'",
    })


def test_explain_reports_the_route_actually_taken():
    _disagree()
    said = cognitive_context.explain_last_route()
    assert "get_battery_status" in said and "tool" in said
    assert "general_qa" not in said, f"explained a route it never took: {said}"
    assert "brain" not in said, f"explained a route it never took: {said}"


def test_describe_reports_the_route_actually_taken():
    _disagree()
    said = cognitive_context.describe_last_understanding()
    assert "get_battery_status" in said
    assert "general_qa" not in said, f"described a route it never took: {said}"


def test_does_not_claim_a_learned_rule_when_the_real_router_used_none():
    """The strategy's learned_rules_used must not be credited for a decision the
    real router made by other means — that would be a fabricated justification."""
    intent_explainer.record_intent_decision(
        {"route": "react", "intent": "react_multi_step", "confidence": 0.9, "reason": "multi_step_task"},
    )
    cognitive_context.set_last_strategy({
        "normalized_text": "open notepad and type hello",
        "chosen_route": "tool",
        "chosen_intent": "local_prefix",
        "learned_rules_used": ["rule_42"],
    })
    said = cognitive_context.explain_last_route()
    assert "react_multi_step" in said
    assert "learned rule" not in said, f"credited a rule the real router did not use: {said}"


def test_credits_a_learned_rule_when_the_real_router_did_use_one():
    intent_explainer.record_intent_decision(
        {"route": "tool", "intent": "open_app", "confidence": 0.99, "reason": "correction"},
        selected_rule="correction_7",
    )
    cognitive_context.set_last_strategy({"normalized_text": "fire up chrome", "chosen_route": "tool", "chosen_intent": "open_app"})
    assert "learned rule" in cognitive_context.explain_last_route()


def test_no_history_is_reported_honestly():
    assert "not have a recent" in cognitive_context.describe_last_understanding()
