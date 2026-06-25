import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import approval_queue as aq


APPROVAL_TOOLS = ["pending_approvals", "approve_action", "reject_action"]


def _route(phrase):
    return _deterministic_router(phrase, {}).get("intent")


def setup_function(_fn):
    aq.clear()


def test_approval_tools_registered():
    for name in APPROVAL_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_approval_tools_whitelisted():
    for name in APPROVAL_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_risk_policy():
    assert aq.requires_approval("low") is False
    assert aq.requires_approval("medium") is False
    assert aq.requires_approval("high") is True
    assert aq.requires_approval("critical") is True


def test_gate_lets_low_risk_through():
    assert aq.gate("x", {}, "low", "do x") is None
    # already approved via the internal token (what approve() injects)
    assert aq.gate("x", {aq._APPROVAL_TOKEN_KEY: aq._INTERNAL_APPROVAL}, "critical", "do x") is None


def test_external_approved_flag_cannot_bypass_gate():
    # A user/router-supplied plain "approved" must NOT bypass the gate.
    g = aq.gate("danger", {"approved": True}, "critical", "click pay")
    assert g is not None and g.get("requires_approval") is True
    assert len(aq.list_pending()) == 1


def test_gate_queues_high_risk():
    g = aq.gate("danger", {"target": "Submit"}, "critical", "click Submit")
    assert g is not None
    assert g.get("requires_approval") is True
    assert g.get("approval_id")
    assert len(aq.list_pending()) == 1


def test_approve_executes_stored_action():
    # Use a benign tool so approval actually runs something verifiable.
    aid = aq.submit("get_idle_time", {}, "high", "idle check")
    assert len(aq.list_pending()) == 1
    res = aq.approve(aid)
    assert res.get("success") is True and res.get("verified") is True
    assert aq.list_pending() == []  # no longer pending


def test_reject_removes_from_pending():
    aid = aq.submit("get_idle_time", {}, "high", "idle check")
    assert aq.reject(aid) is True
    assert aq.list_pending() == []


def test_pending_approvals_tool():
    aq.submit("get_idle_time", {}, "high", "idle check")
    r = execute_tool("pending_approvals", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("count") == 1


def test_approve_action_tool_with_nothing_pending():
    r = execute_tool("approve_action", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("approved") in (0, False, None) or r.get("count", 0) == 0


def test_approve_action_tool_executes_oldest():
    aq.submit("get_idle_time", {}, "high", "idle check")
    r = execute_tool("approve_action", {})
    assert r["success"] is True and r["verified"] is True
    assert aq.list_pending() == []


def test_reject_action_tool():
    aq.submit("get_idle_time", {}, "high", "idle check")
    r = execute_tool("reject_action", {})
    assert r["success"] is True and r["verified"] is True
    assert aq.list_pending() == []


def test_routing():
    assert _route("pending approvals") == "pending_approvals"
    assert _route("show approvals") == "pending_approvals"
    assert _route("approve") == "approve_action"
    assert _route("approve action") == "approve_action"
    assert _route("reject") == "reject_action"
    assert _route("reject action") == "reject_action"
