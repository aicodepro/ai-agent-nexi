import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _context(**overrides):
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


@pytest.mark.parametrize(
    "text, expected_route, expected_intent",
    [
        ("stop", "interrupt", "stop_speaking"),
        ("cancel", "cancel", "cancel"),
        ("sleep", "sleep", "sleep"),
        ("wake up", "wake", "wake"),
    ],
)
def test_immediate_controls_do_not_call_groq(monkeypatch, text, expected_route, expected_intent):
    from engine.groq_intent_router_v2 import route_intent_v2

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "true")

    with patch("engine.groq_intent_router_v2.requests.post") as groq_post:
        result = route_intent_v2(text, source="typed", context=_context())

    groq_post.assert_not_called()
    assert result["route"] == expected_route
    assert result["intent"] == expected_intent
    assert result["should_call_gemini"] is False
    assert result["should_call_tool"] is False


def test_open_without_target_asks_for_app(monkeypatch):
    from engine.groq_intent_router_v2 import route_intent_v2

    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = route_intent_v2("open", source="typed", context=_context())

    assert result["route"] == "clarify"
    assert result["intent"] == "open_app"
    assert result["missing_slots"] == ["app_name"]
    assert result["expects_user_reply"] is True
    assert result["clarification_question"] == "Which app should I open?"
    assert result["should_call_tool"] is False


def test_chrome_after_open_routes_to_open_app():
    from engine.groq_intent_router_v2 import route_intent_v2

    result = route_intent_v2(
        "chrome",
        source="typed",
        context=_context(pending_followup={"followup_type": "open_app"}),
    )

    assert result["route"] == "tool"
    assert result["intent"] == "open_app"
    assert result["slots"]["app_name"] == "chrome"
    assert result["should_call_gemini"] is False


def test_youtube_after_open_routes_to_open_website():
    from engine.groq_intent_router_v2 import route_intent_v2

    result = route_intent_v2(
        "youtube",
        source="typed",
        context=_context(pending_followup={"followup_type": "open_app"}),
    )

    assert result["route"] == "tool"
    assert result["intent"] == "open_website"
    assert result["slots"]["url"] == "youtube.com"
    assert result["should_call_gemini"] is False


def test_search_without_query_asks_for_query(monkeypatch):
    from engine.groq_intent_router_v2 import route_intent_v2

    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = route_intent_v2("search", source="typed", context=_context())

    assert result["route"] == "clarify"
    assert result["intent"] == "web_search"
    assert result["missing_slots"] == ["query"]
    assert result["expects_user_reply"] is True
    assert result["clarification_question"] == "What should I search for?"
    assert result["should_call_tool"] is False


def test_ronaldo_after_search_routes_to_web_search():
    from engine.groq_intent_router_v2 import route_intent_v2

    result = route_intent_v2(
        "ronaldo",
        source="typed",
        context=_context(pending_followup={"followup_type": "web_search"}),
    )

    assert result["route"] == "tool"
    assert result["intent"] == "web_search"
    assert result["slots"]["query"] == "ronaldo"
    assert result["should_call_gemini"] is False


def test_unknown_input_falls_back_to_brain(monkeypatch):
    # Policy change: when no feature matches, hand off to the brain (Gemini) instead of
    # dead-ending on "I didn't understand". (Bare missing-slot cases still clarify.)
    from engine.groq_intent_router_v2 import route_intent_v2

    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = route_intent_v2("flibbertigibbet plover", source="typed", context=_context())
    assert result["route"] == "brain"
    assert result["should_call_gemini"] is True
    assert result["should_call_tool"] is False


def test_low_confidence_result_clarifies(monkeypatch):
    import engine.groq_intent_router_v2 as router

    monkeypatch.setattr(
        router,
        "_route_with_groq",
        lambda _text, _ctx: {
            "route": "brain",
            "intent": "general_qa",
            "domain": "conversation",
            "confidence": 0.2,
            "slots": {},
            "missing_slots": [],
            "expects_user_reply": False,
            "reason": "ambiguous",
        },
    )

    result = router.route_intent_v2("maybe do the thing", source="typed", context=_context())
    assert result["route"] == "clarify"
    assert result["expects_user_reply"] is True
    assert result["should_call_gemini"] is False
    assert result["should_call_tool"] is False
