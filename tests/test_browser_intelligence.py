import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import browser_intelligence as bi


BROWSER_TOOLS = ["read_current_page", "list_browser_tabs", "read_browser_console"]

_FAKE = [
    {"type": "page", "title": "Example Domain", "url": "https://example.com", "webSocketDebuggerUrl": "ws://x/1"},
    {"type": "page", "title": "GitHub", "url": "https://github.com", "webSocketDebuggerUrl": "ws://x/2"},
]


def _route(phrase):
    return _deterministic_router(phrase, {}).get("intent")


@pytest.fixture
def with_browser(monkeypatch):
    monkeypatch.setattr(bi, "_fetch_targets", lambda: list(_FAKE))
    monkeypatch.setattr(bi, "_page_text", lambda t: "Example Domain. This domain is for use in illustrative examples.")
    monkeypatch.setattr(bi, "_capture_console", lambda t: ["error: ReferenceError x is not defined"])
    return _FAKE


@pytest.fixture
def no_browser(monkeypatch):
    monkeypatch.setattr(bi, "_fetch_targets", lambda: [])
    return None


def test_browser_tools_registered():
    for name in BROWSER_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_browser_tools_whitelisted():
    for name in BROWSER_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_read_current_page_with_browser(with_browser):
    r = execute_tool("read_current_page", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "read_current_page"
    assert r.get("available") is True
    assert r.get("title") == "Example Domain"
    assert r.get("url") == "https://example.com"
    assert "illustrative" in (r.get("text") or "")


def test_read_current_page_no_browser_is_graceful(no_browser):
    r = execute_tool("read_current_page", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("available") is False


def test_list_browser_tabs_with_browser(with_browser):
    r = execute_tool("list_browser_tabs", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("tab_count") == 2
    assert {t["url"] for t in r.get("tabs", [])} == {"https://example.com", "https://github.com"}


def test_list_browser_tabs_no_browser(no_browser):
    r = execute_tool("list_browser_tabs", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("tab_count") == 0
    assert r.get("available") is False


def test_read_browser_console_with_browser(with_browser):
    r = execute_tool("read_browser_console", {})
    assert r["success"] is True and r["verified"] is True
    assert any("ReferenceError" in e for e in r.get("errors", []))


def test_read_browser_console_no_browser(no_browser):
    r = execute_tool("read_browser_console", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("available") is False


def test_safe_targets_never_raises(monkeypatch):
    def boom():
        raise OSError("connection refused")
    monkeypatch.setattr(bi, "_fetch_targets", boom)
    assert bi._safe_targets() == []


def test_routing_read_page():
    for phrase in ("read this page", "read the page", "summarize this page", "whats on this page"):
        assert _route(phrase) == "read_current_page", f"{phrase!r} mis-routed"


def test_routing_list_tabs():
    for phrase in ("list my tabs", "what tabs are open", "show my tabs"):
        assert _route(phrase) == "list_browser_tabs", f"{phrase!r} mis-routed"


def test_routing_console():
    for phrase in ("check console errors", "read the console", "any console errors"):
        assert _route(phrase) == "read_browser_console", f"{phrase!r} mis-routed"
