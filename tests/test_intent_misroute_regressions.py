"""Regressions for verified misroutes that made NEXI 'feel like a bot' — genuine
questions hijacked into tools/react by over-eager deterministic matchers.

Each case was reproduced end-to-end before the fix (compound splitter over-split on
`next` and noun-homograph verbs; `tell_time` matched the substring 'the time';
`_weather_match` fired on any weather keyword). Deterministic-only (LLM off) so the
assertions are stable.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch):
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "none")


def _route(q):
    from engine.groq_intent_router_v2 import route_intent_v2
    return route_intent_v2(q, source="typed")


# questions that must NOT be executed as tools/react
@pytest.mark.parametrize("q", [
    "what is the next step",
    "play the next song",
    "compare bing and google",
    "tell me about python and go",
    "what is the time complexity of quicksort",
    "explain the time value of money",
    "why is the weather so unpredictable",
])
def test_questions_are_not_hijacked_into_tools(q):
    d = _route(q)
    assert d["route"] in {"brain", "clarify"}, f"{q!r} misrouted to {d['route']}/{d['intent']}"


# real commands that must still work
@pytest.mark.parametrize("q,route", [
    ("what time is it", "tool"),
    ("what is the weather", "tool"),
    ("weather in london", "tool"),
    ("open notepad and type hello world", "react"),
    ("open chrome and then search cats", "react"),
])
def test_real_commands_still_route(q, route):
    d = _route(q)
    assert d["route"] == route, f"{q!r} -> {d['route']}/{d['intent']} (wanted {route})"


def test_compound_splitter_does_not_oversplit():
    from engine.router.compound import split_steps
    # noun homographs and 'next' must not create fake steps
    assert split_steps("what is the next step") == ["what is the next step"]
    assert split_steps("tell me about python and go") == ["tell me about python and go"]
    assert split_steps("compare bing and google") == ["compare bing and google"]
    # genuine multi-step must still split
    assert len(split_steps("open notepad and type hello")) == 2
    assert len(split_steps("open chrome then search cats")) == 2


# The counterexamples to the veto above. A question about the user's OWN machine, or about
# Nexi itself, is a COMMAND — the awareness tools exist precisely to answer it. A blanket
# "question prefix -> never a tool" rule silently broke all of these, because they open with
# "what is" / "what are" / "why is" exactly like a general-knowledge question does.
@pytest.mark.parametrize("q", [
    "what is my system status",
    "what are you monitoring",
    "why is my pc slow",
    "what is my ip address",
])
def test_questions_about_my_own_machine_are_still_commands(q):
    d = _route(q)
    assert d["route"] == "tool", f"{q!r} -> {d['route']}/{d['intent']} (self-referential query must reach a tool)"
