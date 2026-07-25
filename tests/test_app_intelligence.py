import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import app_intelligence as ai


APP_TOOLS = ["resolve_app_for_task", "open_app_for_task"]


def _route(phrase):
    return _deterministic_router(phrase, {})


def test_app_tools_registered():
    for name in APP_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_app_tools_whitelisted():
    for name in APP_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_resolve_for_task_known_categories():
    for task, cat in [("coding", "coding"), ("presentation", "presentation"),
                      ("browsing", "browsing"), ("spreadsheet", "spreadsheet")]:
        r = ai.resolve_for_task(task)
        assert r["category"] == cat
        candidates = [c[1] for c in ai._TASK_APPS[cat]]
        assert r["app"] in candidates, f"{task} -> {r['app']} not in {candidates}"
        assert 0.0 < r["confidence"] <= 1.0


def test_resolve_for_task_synonyms():
    assert ai.resolve_for_task("programming")["category"] == "coding"
    assert ai.resolve_for_task("make slides")["category"] == "presentation"
    assert ai.resolve_for_task("browse the web")["category"] == "browsing"


def test_resolve_for_task_unknown_falls_back():
    r = ai.resolve_for_task("frobnicate widgets")
    assert isinstance(r["app"], str) and r["app"]
    assert 0.0 < r["confidence"] <= 1.0


def test_resolve_app_for_task_executes_and_verifies():
    r = execute_tool("resolve_app_for_task", {"task": "coding"})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "resolve_app_for_task"
    assert isinstance(r.get("app"), str) and r["app"]
    assert 0.0 < r.get("confidence", 0) <= 1.0


def test_resolve_app_for_task_missing_task_asks():
    r = execute_tool("resolve_app_for_task", {})
    assert r.get("verified") is not True
    assert r.get("expects_user_reply") is True


def test_open_app_for_task_uses_opener(monkeypatch):
    opened = []
    monkeypatch.setattr(ai, "_open_app", lambda name: opened.append(name) or {"success": True, "verified": True, "message": f"Opening {name}.", "tool": "open_app"})
    r = execute_tool("open_app_for_task", {"task": "coding"})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "open_app_for_task"
    assert len(opened) == 1 and opened[0]


def test_routing_resolve_variants():
    for phrase in ("best app for coding", "what app should i use for presentation", "which app for browsing"):
        r = _route(phrase)
        assert r.get("intent") == "resolve_app_for_task", f"{phrase!r} -> {r.get('intent')}"
        assert r.get("slots", {}).get("task"), f"{phrase!r} missing task slot"


def test_routing_open_best_app_for():
    r = _route("open the best app for coding")
    assert r.get("intent") == "open_app_for_task", f"-> {r.get('intent')}"
    assert r.get("slots", {}).get("task") == "coding"
