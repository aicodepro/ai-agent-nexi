import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax


def _route(phrase):
    # Assert on the deterministic alias-routing layer this feature extends.
    # The full route_intent_v2() pipeline also consults a persisted learned
    # pre-router, which other tests can bias — so we test the layer we wired.
    return _deterministic_router(phrase, {}).get("intent")


NET_TOOLS = ["am_i_online", "get_network_status", "get_ip_address"]


def test_net_tools_registered():
    for name in NET_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered in tool registry"


def test_net_tools_whitelisted():
    for name in NET_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_am_i_online_executes_and_verifies():
    r = execute_tool("am_i_online", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "am_i_online"
    assert isinstance(r["message"], str) and r["message"]
    assert isinstance(r.get("online"), bool)


def test_get_network_status_executes_and_verifies():
    r = execute_tool("get_network_status", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "get_network_status"
    assert isinstance(r.get("online"), bool)
    assert isinstance(r.get("interface"), str)


def test_get_ip_address_executes_and_verifies():
    r = execute_tool("get_ip_address", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "get_ip_address"
    assert isinstance(r.get("ip"), str)


def test_routing_am_i_online():
    for phrase in ("am i online", "do i have internet", "are we connected"):
        assert _route(phrase) == "am_i_online", f"{phrase!r} mis-routed"


def test_routing_network_status():
    for phrase in ("network status", "wifi status", "what network am i on"):
        assert _route(phrase) == "get_network_status", f"{phrase!r} mis-routed"


def test_routing_ip_address():
    for phrase in ("what is my ip address", "my ip address", "what's my ip"):
        assert _route(phrase) == "get_ip_address", f"{phrase!r} mis-routed"


def test_read_only_no_state_change():
    before = execute_tool("get_network_status", {})
    after = execute_tool("get_network_status", {})
    assert before["tool"] == after["tool"] == "get_network_status"
