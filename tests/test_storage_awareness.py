import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax


def _route(phrase):
    # Assert on the deterministic alias-routing layer this feature extends
    # (route_intent_v2's learned pre-router can be biased by other tests).
    return _deterministic_router(phrase, {}).get("intent")


STORAGE_TOOLS = ["get_disk_space", "is_disk_full", "get_battery_status"]


def test_storage_tools_registered():
    for name in STORAGE_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered in tool registry"


def test_storage_tools_whitelisted():
    for name in STORAGE_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_get_disk_space_executes_and_verifies():
    r = execute_tool("get_disk_space", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "get_disk_space"
    assert isinstance(r["message"], str) and r["message"]
    assert isinstance(r.get("free_gb"), (int, float))
    assert isinstance(r.get("total_gb"), (int, float))
    assert r.get("total_gb") >= r.get("free_gb")


def test_is_disk_full_executes_and_verifies():
    r = execute_tool("is_disk_full", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "is_disk_full"
    assert isinstance(r.get("full"), bool)


def test_get_battery_status_executes_and_verifies():
    r = execute_tool("get_battery_status", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "get_battery_status"
    assert isinstance(r.get("has_battery"), bool)
    if r.get("has_battery"):
        assert isinstance(r.get("percent"), (int, float))
        assert isinstance(r.get("plugged"), bool)


def test_routing_disk_space():
    for phrase in ("how much disk space do i have", "disk space", "how much storage do i have"):
        assert _route(phrase) == "get_disk_space", f"{phrase!r} mis-routed"


def test_routing_is_disk_full():
    for phrase in ("is my disk full", "is my drive full", "am i running out of space"):
        assert _route(phrase) == "is_disk_full", f"{phrase!r} mis-routed"


def test_routing_battery():
    for phrase in ("battery status", "how much battery do i have", "am i charging"):
        assert _route(phrase) == "get_battery_status", f"{phrase!r} mis-routed"


def test_read_only_idempotent():
    a = execute_tool("get_disk_space", {})
    b = execute_tool("get_disk_space", {})
    assert a["tool"] == b["tool"] == "get_disk_space"
    assert a["success"] is True and b["success"] is True
