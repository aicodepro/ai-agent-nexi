import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import browser_intelligence as bi
from engine import approval_queue as aq


WRITE_TOOLS = ["browser_click", "browser_fill"]


def _route(phrase):
    return _deterministic_router(phrase, {})


def setup_function(_fn):
    aq.clear()


def test_write_tools_registered():
    for name in WRITE_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_write_tools_whitelisted():
    for name in WRITE_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_browser_click_requires_approval():
    r = execute_tool("browser_click", {"target": "Login"})
    assert r.get("requires_approval") is True
    assert r.get("verified") is not True
    assert len(aq.list_pending()) == 1


def test_browser_click_after_approval(monkeypatch):
    clicked = []
    monkeypatch.setattr(bi, "_perform_browser_click", lambda target: clicked.append(target) or True)
    execute_tool("browser_click", {"target": "Login"})
    done = execute_tool("approve_action", {})
    assert done["success"] is True and done["verified"] is True
    assert clicked == ["Login"]


def test_browser_click_no_target_asks():
    r = execute_tool("browser_click", {})
    assert r.get("verified") is not True
    assert r.get("expects_user_reply") is True


def test_browser_fill_requires_approval():
    r = execute_tool("browser_fill", {"field": "search", "value": "python"})
    assert r.get("requires_approval") is True
    assert len(aq.list_pending()) == 1


def test_browser_fill_after_approval(monkeypatch):
    filled = []
    monkeypatch.setattr(bi, "_perform_browser_fill", lambda field, value: filled.append((field, value)) or True)
    execute_tool("browser_fill", {"field": "search", "value": "python"})
    done = execute_tool("approve_action", {})
    assert done["success"] is True
    assert filled == [("search", "python")]


def test_browser_fill_missing_asks():
    r = execute_tool("browser_fill", {"field": "search"})
    assert r.get("verified") is not True
    assert r.get("expects_user_reply") is True


def test_routing_browser_click_link():
    r = _route("click the login link")
    assert r.get("intent") == "browser_click"
    assert "login" in r.get("slots", {}).get("target", "").lower()


def test_routing_browser_click_on_page():
    r = _route("click submit on the page")
    assert r.get("intent") == "browser_click"
    assert "submit" in r.get("slots", {}).get("target", "").lower()


def test_routing_browser_fill():
    r = _route("fill the search field with python tutorials")
    assert r.get("intent") == "browser_fill"
    assert r.get("slots", {}).get("field", "").strip() == "search"
    assert "python" in r.get("slots", {}).get("value", "")


def test_generic_click_still_goes_to_computer_use():
    r = _route("click the submit button")
    assert r.get("intent") == "click_ui_element"
