import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax


RUNTIME_TOOLS = ["show_diagnostics", "get_monitor_state", "echo_guard_status", "get_hud_state"]


def _route(phrase):
    return _deterministic_router(phrase, {}).get("intent")


def test_runtime_tools_registered():
    for name in RUNTIME_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_runtime_tools_whitelisted():
    for name in RUNTIME_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_all_execute_and_verify():
    for name in RUNTIME_TOOLS:
        r = execute_tool(name, {})
        assert r["success"] is True and r["verified"] is True, f"{name} not verified: {r}"
        assert r["tool"] == name
        assert isinstance(r["message"], str) and r["message"]


def test_show_diagnostics_payload():
    r = execute_tool("show_diagnostics", {})
    assert isinstance(r.get("voice_state"), str)


def test_get_monitor_state_payload():
    r = execute_tool("get_monitor_state", {})
    assert isinstance(r.get("panel_count"), int)


def test_echo_guard_status_payload():
    r = execute_tool("echo_guard_status", {})
    assert isinstance(r.get("in_cooldown"), bool)
    assert isinstance(r.get("cooldown_remaining_ms"), int)


def test_get_hud_state_payload():
    r = execute_tool("get_hud_state", {})
    assert isinstance(r.get("mode"), str)
    assert "active_app" in r


def test_routing_show_diagnostics():
    for phrase in ("show diagnostics", "voice diagnostics", "show voice diagnostics"):
        assert _route(phrase) == "show_diagnostics", f"{phrase!r} mis-routed"


def test_routing_monitor_state():
    for phrase in ("monitor state", "what are you monitoring", "monitor status"):
        assert _route(phrase) == "get_monitor_state", f"{phrase!r} mis-routed"


def test_routing_echo_guard():
    for phrase in ("echo guard status", "are you in cooldown", "tts cooldown"):
        assert _route(phrase) == "echo_guard_status", f"{phrase!r} mis-routed"


def test_routing_hud_state():
    for phrase in ("show hud", "hud state", "command center"):
        assert _route(phrase) == "get_hud_state", f"{phrase!r} mis-routed"
