import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import computer_use as cu
from engine import approval_queue as aq


@pytest.fixture(autouse=True)
def _disable_llm_safety_gate(monkeypatch):
    """The LLM safety gate calls the Groq safety model. Offline (no GROQ_API_KEY) it fails
    CLOSED and blocks every medium+ risk tool, so nothing here would reach the approval /
    confirmation logic these tests exist to check. Disable it locally rather than suite-wide:
    a blocked tool is the SAFE default for a test run, since an allowed one really launches
    apps and moves the mouse."""
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")




CU_TOOLS = ["screen_read", "click_ui_element", "type_text"]


def _route(phrase):
    return _deterministic_router(phrase, {})


def setup_function(_fn):
    aq.clear()


def test_cu_tools_registered():
    for name in CU_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_cu_tools_whitelisted():
    for name in CU_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_screen_read_with_text(monkeypatch):
    monkeypatch.setattr(cu, "_capture_screen_text", lambda: "Error: file not found in build output")
    r = execute_tool("screen_read", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("available") is True
    assert "file not found" in (r.get("text") or "")


def test_screen_read_empty_is_graceful(monkeypatch):
    monkeypatch.setattr(cu, "_capture_screen_text", lambda: "")
    r = execute_tool("screen_read", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("available") is False


def test_click_requires_approval_first():
    r = execute_tool("click_ui_element", {"target": "Submit"})
    assert r.get("requires_approval") is True
    assert r.get("verified") is not True
    assert len(aq.list_pending()) == 1


def test_click_executes_after_approval(monkeypatch):
    clicked = []
    monkeypatch.setattr(cu, "_perform_click", lambda target: clicked.append(target) or True)
    queued = execute_tool("click_ui_element", {"target": "Submit"})
    assert queued.get("requires_approval") is True
    done = execute_tool("approve_action", {})
    assert done["success"] is True and done["verified"] is True
    assert clicked == ["Submit"]


def test_click_direct_with_internal_token(monkeypatch):
    monkeypatch.setattr(cu, "_perform_click", lambda target: True)
    r = execute_tool("click_ui_element", {"target": "OK", aq._APPROVAL_TOKEN_KEY: aq._INTERNAL_APPROVAL})
    assert r["success"] is True and r["verified"] is True
    assert r.get("performed") is True


def test_external_approved_flag_does_not_bypass(monkeypatch):
    # Security: a plain "approved" slot (as a router/LLM could emit) must NOT execute.
    called = []
    monkeypatch.setattr(cu, "_perform_click", lambda target: called.append(target) or True)
    r = execute_tool("click_ui_element", {"target": "Pay", "approved": True})
    assert r.get("requires_approval") is True
    assert r.get("verified") is not True
    assert called == []


def test_click_no_target_asks():
    r = execute_tool("click_ui_element", {})
    assert r.get("verified") is not True
    assert r.get("expects_user_reply") is True


def test_type_text_requires_approval():
    r = execute_tool("type_text", {"text": "hello world"})
    assert r.get("requires_approval") is True
    assert len(aq.list_pending()) == 1


def test_type_text_after_approval(monkeypatch):
    typed = []
    monkeypatch.setattr(cu, "_perform_type", lambda text: typed.append(text) or True)
    execute_tool("type_text", {"text": "hello world"})
    done = execute_tool("approve_action", {})
    assert done["success"] is True
    assert typed == ["hello world"]


def test_routing_screen_read():
    for phrase in ("read my screen", "read the screen", "whats on my screen"):
        assert _route(phrase).get("intent") == "screen_read", f"{phrase!r} mis-routed"


def test_routing_click():
    r = _route("click the submit button")
    assert r.get("intent") == "click_ui_element"
    assert "submit" in r.get("slots", {}).get("target", "").lower()


def test_routing_type():
    r = _route("type out hello world")
    assert r.get("intent") == "type_text"
    assert r.get("slots", {}).get("text") == "hello world"
