"""Idea #59 — Tool-RAG (RAG-MCP): narrow the tool list semantically before the LLM
sees it. https://arxiv.org/abs/2505.03275

The router used to hand the model all 113 tools (~35KB JSON) on every fuzzy route;
a model asked to pick 1-of-113 picks badly. Measured here: 35,380 -> ~4,092 chars
(88% smaller) with 12/12 recall.

The dangerous failure is RECALL, not size: a shorter list that drops the correct
tool is a regression. So these tests pin the safety properties — never narrow when
cold (that would also drag in the ~83s embedder build), never return empty.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine.groq_intent_router_v2 as router

CAPS = [
    {"name": "get_battery_status", "description": "Battery"},
    {"name": "tell_time", "description": "Time"},
    {"name": "open_app", "description": "Open app"},
    {"name": "screen_read", "description": "Read screen"},
]


class _Cand:
    def __init__(self, intent):
        self.intent = intent


class _Match:
    def __init__(self, intents):
        self.candidates = [_Cand(i) for i in intents]


class _Semantic:
    def __init__(self, intents):
        self._intents = intents

    def match(self, _text):
        return _Match(self._intents)


class _Router:
    def __init__(self, intents):
        self.semantic = _Semantic(intents)


def _warm(monkeypatch, intents):
    import engine.router as rp
    monkeypatch.setattr(rp, "_ROUTER", _Router(intents), raising=False)


def test_narrows_to_semantic_candidates(monkeypatch):
    _warm(monkeypatch, ["get_battery_status", "tell_time"])
    out = router._rag_filter_capabilities("what is my battery", CAPS)
    names = {c["name"] for c in out}
    assert names == {"get_battery_status", "tell_time"}, names
    assert len(out) < len(CAPS)


def test_never_narrows_when_the_index_is_cold(monkeypatch):
    """A cold router must return the FULL list — narrowing would require building
    the e5 embedder (~83s) inside the turn, which froze the UI once already."""
    import engine.router as rp
    monkeypatch.setattr(rp, "_ROUTER", None, raising=False)
    monkeypatch.setattr(rp, "get_router", lambda: pytest.fail("built the index to filter tools"))
    assert router._rag_filter_capabilities("what is my battery", CAPS) == CAPS


def test_falls_back_to_full_list_when_nothing_matches(monkeypatch):
    """If the narrowing would drop everything, send everything — a list missing the
    right tool is worse than a long one."""
    _warm(monkeypatch, ["some_unknown_intent"])
    assert router._rag_filter_capabilities("gibberish", CAPS) == CAPS


def test_semantic_failure_degrades_to_full_list(monkeypatch):
    class _Boom:
        @property
        def semantic(self):
            raise RuntimeError("index exploded")

    import engine.router as rp
    monkeypatch.setattr(rp, "_ROUTER", _Boom(), raising=False)
    assert router._rag_filter_capabilities("what is my battery", CAPS) == CAPS


def test_empty_capabilities_are_passed_through(monkeypatch):
    _warm(monkeypatch, ["get_battery_status"])
    assert router._rag_filter_capabilities("x", []) == []


def test_topk_is_configurable(monkeypatch):
    _warm(monkeypatch, ["get_battery_status", "tell_time", "open_app"])
    monkeypatch.setenv("NEXI_TOOL_RAG_TOPK", "1")
    out = router._rag_filter_capabilities("what is my battery", CAPS)
    assert {c["name"] for c in out} == {"get_battery_status"}


def test_can_be_disabled(monkeypatch):
    _warm(monkeypatch, ["get_battery_status"])
    monkeypatch.setenv("NEXI_TOOL_RAG_TOPK", "0")
    assert router._rag_filter_capabilities("what is my battery", CAPS) == CAPS
