import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import skill_library as sl


SKILL_TOOLS = ["list_skills", "describe_skill"]


def _route(phrase):
    return _deterministic_router(phrase, {})


def test_skill_tools_registered():
    for name in SKILL_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_skill_tools_whitelisted():
    for name in SKILL_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_capability_catalog():
    cat = sl.capability_catalog()
    assert cat["total"] > 0
    assert isinstance(cat["categories"], dict) and cat["categories"]
    assert "system" in cat["categories"]
    for _name, info in cat["categories"].items():
        assert info["count"] >= 1
        assert isinstance(info["tools"], list)


def test_list_skills_executes_and_verifies():
    r = execute_tool("list_skills", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "list_skills"
    assert r.get("total", 0) > 0
    assert isinstance(r.get("categories"), dict)


def test_describe_skill_known():
    r = execute_tool("describe_skill", {"name": "get_battery_status"})
    assert r["success"] is True and r["verified"] is True
    assert r.get("found") is True
    assert r.get("skill") == "get_battery_status"
    assert isinstance(r.get("description"), str) and r["description"]


def test_describe_skill_by_alias():
    r = execute_tool("describe_skill", {"name": "battery status"})
    assert r["success"] is True and r["verified"] is True
    assert r.get("found") is True


def test_describe_skill_unknown_is_honest():
    r = execute_tool("describe_skill", {"name": "teleportation device"})
    assert r["success"] is True and r["verified"] is True
    assert r.get("found") is False


def test_describe_skill_missing_name_asks():
    r = execute_tool("describe_skill", {})
    assert r.get("verified") is not True
    assert r.get("expects_user_reply") is True


def test_routing_list_skills():
    for phrase in ("what can you do", "list your skills", "what skills do you have"):
        assert _route(phrase).get("intent") == "list_skills", f"{phrase!r} mis-routed"


def test_routing_describe_skill():
    for phrase, expect in [("tool help battery", "battery"),
                           ("describe skill camera", "camera"),
                           ("describe the camera skill", "camera")]:
        r = _route(phrase)
        assert r.get("intent") == "describe_skill", f"{phrase!r} -> {r.get('intent')}"
        assert expect in (r.get("slots", {}).get("name", "")), f"{phrase!r} slot={r.get('slots')}"
