import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax


OS_TOOLS = [
    "get_active_window", "what_am_i_working_on", "get_system_state",
    "why_is_pc_slow", "get_running_apps", "get_idle_time",
]


def _route(phrase):
    return _deterministic_router(phrase, {}).get("intent")


def test_os_tools_registered():
    for name in OS_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_os_tools_whitelisted():
    for name in OS_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_existing_os_tools_execute_and_verify():
    for name in ("get_active_window", "what_am_i_working_on", "get_system_state", "why_is_pc_slow"):
        r = execute_tool(name, {})
        assert r["success"] is True and r["verified"] is True, f"{name} not verified: {r}"
        assert r["tool"] == name
        assert isinstance(r["message"], str) and r["message"]


def test_get_running_apps_executes_and_verifies():
    r = execute_tool("get_running_apps", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "get_running_apps"
    assert isinstance(r.get("count"), int) and r["count"] >= 1
    assert isinstance(r.get("apps"), list)


def test_get_idle_time_executes_and_verifies():
    r = execute_tool("get_idle_time", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "get_idle_time"
    assert isinstance(r.get("idle_seconds"), (int, float))
    assert r["idle_seconds"] >= 0


def test_routing_running_apps():
    for phrase in ("what apps are running", "list running apps", "what programs are open"):
        assert _route(phrase) == "get_running_apps", f"{phrase!r} mis-routed"


def test_routing_idle_time():
    for phrase in ("how long have i been idle", "idle time", "how long was i away"):
        assert _route(phrase) == "get_idle_time", f"{phrase!r} mis-routed"


def test_read_only_idempotent():
    a = execute_tool("get_running_apps", {})
    b = execute_tool("get_running_apps", {})
    assert a["success"] is True and b["success"] is True
