import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _ctx():
    return {
        "source": "test",
        "pending_clarification": {},
        "pending_followup": {},
        "active_workflow": {},
        "active_training": {},
        "latest_output": {"available": False},
        "recent_turns": [],
    }


def _route(monkeypatch, text):
    # Force deterministic-only routing (no network) so the dataset is hermetic.
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "deterministic")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    import engine.correction_learner as learner

    monkeypatch.setattr(learner, "apply_correction", lambda _t: {"matched": False})
    from engine.groq_intent_router_v2 import route_intent_v2

    return route_intent_v2(text, source="typed", context=_ctx())


# (text, expected_route, expected_intent)
FEATURE_CASES = [
    ("open yt", "tool", "open_website"),
    ("open youtube", "tool", "open_website"),
    ("play lofi on yt", "tool", "search_youtube"),
    ("search youtube for python tutorial", "tool", "search_youtube"),
    ("youtube pe search karo cats", "tool", "search_youtube"),
    ("chrome kholo", "tool", "open_app"),
    ("open chrome", "tool", "open_app"),
    ("search ronaldo", "tool", "web_search"),
    ("what time is it", "tool", "tell_time"),
    ("tell me a joke", "tool", "tell_joke"),
    ("open a new tab", "tool", "browser_new_tab"),
    ("close the tab", "tool", "browser_close_tab"),
    ("go fullscreen", "tool", "browser_fullscreen"),
    ("pause the video", "tool", "media_pause"),
    ("resume the video", "tool", "media_resume"),
    ("weather in london", "tool", "weather_lookup"),
    ("what's the weather", "tool", "weather_lookup"),
    ("check my internet speed", "tool", "internet_speed_test"),
    ("remember my project name is oryn", "memory", "remember"),
]

KNOWLEDGE_CASES = [
    ("what is docker", "brain"),
    ("explain photosynthesis", "brain"),
    ("who is ronaldo", "brain"),
]


import pytest


@pytest.mark.parametrize("text, route, intent", FEATURE_CASES)
def test_feature_commands_never_route_to_brain(monkeypatch, text, route, intent):
    result = _route(monkeypatch, text)
    assert result["route"] != "brain", f"{text!r} leaked to brain"
    assert result["route"] == route, f"{text!r} -> {result['route']} expected {route}"
    assert result["intent"] == intent, f"{text!r} -> {result['intent']} expected {intent}"


@pytest.mark.parametrize("text, route", KNOWLEDGE_CASES)
def test_knowledge_questions_route_to_brain(monkeypatch, text, route):
    result = _route(monkeypatch, text)
    assert result["route"] == route


def test_no_feature_command_routes_to_brain(monkeypatch):
    # Hard guarantee for the whole feature dataset.
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "deterministic")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import engine.correction_learner as learner

    monkeypatch.setattr(learner, "apply_correction", lambda _t: {"matched": False})
    from engine.groq_intent_router_v2 import route_intent_v2

    leaks = []
    for text, route, intent in FEATURE_CASES:
        d = route_intent_v2(text, source="typed", context=_ctx())
        if d["route"] == "brain":
            leaks.append(text)
    assert not leaks, f"feature commands leaked to brain: {leaks}"


def test_every_router_tool_is_registered():
    from engine.tool_manifest_loader import router_tool_names
    from engine.tool_registry import get_tool

    for name in router_tool_names():
        assert get_tool(name) is not None, f"router exposed unregistered tool {name}"

