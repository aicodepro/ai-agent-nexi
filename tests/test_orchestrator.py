import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.groq_intent_router_v2 import _deterministic_router
from engine.tool_registry import get_tool, execute_tool
from engine import intent_taxonomy as tax
from engine import feature_requests as fr


def _route(p):
    return _deterministic_router(p, {})


# ── Fix: conversational → brain, not clarify ─────────────────────────────────
def test_bye_routes_to_brain():
    for p in ("bye", "goodbye", "see you later", "good night"):
        r = _route(p)
        assert r["route"] == "brain" and r["intent"] == "social_close", f"{p!r} -> {r}"


def test_thanks_routes_to_brain():
    for p in ("thanks", "thank you"):
        r = _route(p)
        assert r["route"] == "brain" and r["intent"] == "social_reply", f"{p!r} -> {r}"


def test_long_sentence_routes_to_brain_not_clarify():
    r = _route("the intent system is broken help me plan the fix")
    assert r["route"] == "brain" and r["intent"] == "general_qa", f"-> {r}"


def test_short_unknown_still_clarifies():
    r = _route("blorp")
    assert r["route"] == "clarify"


def test_social_intents_whitelisted():
    assert "social_close" in tax.BRAIN_INTENTS
    assert "social_reply" in tax.BRAIN_INTENTS


# ── Fix: feature_gap → request_feature ───────────────────────────────────────
def test_feature_gap_route_allowed():
    assert "feature_gap" in tax.ALLOWED_ROUTES


def test_create_monitor_routes_to_request_feature():
    r = _route("create a github issue monitor")
    assert r["intent"] == "request_feature", f"-> {r}"
    assert "monitor" in r.get("slots", {}).get("capability", "").lower()


def test_build_tool_that_routes_to_request_feature():
    r = _route("build a tool that watches my downloads")
    assert r["intent"] == "request_feature", f"-> {r}"


def test_create_folder_is_not_feature_gap():
    r = _route("create folder on desktop")
    assert r["intent"] != "request_feature"


def test_feature_tools_registered_and_whitelisted():
    for n in ("request_feature", "list_feature_requests"):
        assert get_tool(n) is not None
        assert n in tax.ALLOWED_INTENTS and n in tax.TOOL_INTENTS


def test_request_feature_tool_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(fr, "_STORE", tmp_path / "fr.json")
    r = execute_tool("request_feature", {"capability": "github issue monitor"})
    assert r["success"] is True and r["verified"] is True
    assert r.get("request_id")
    assert fr.list_requests() and fr.list_requests()[0]["status"] == "proposed"


def test_request_feature_missing_capability_asks(monkeypatch, tmp_path):
    monkeypatch.setattr(fr, "_STORE", tmp_path / "fr.json")
    r = execute_tool("request_feature", {})
    assert r.get("verified") is not True and r.get("expects_user_reply") is True


def test_list_feature_requests_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(fr, "_STORE", tmp_path / "fr.json")
    execute_tool("request_feature", {"capability": "x monitor"})
    r = execute_tool("list_feature_requests", {})
    assert r["success"] is True and r.get("count") >= 1


def test_routing_list_feature_requests():
    assert _route("list feature requests").get("intent") == "list_feature_requests"
