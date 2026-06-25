import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine.integrations.crewai_style import workflow_engine as we
from engine.integrations.crewai_style import nexi_tool_proxy as proxy


WF_TOOLS = [
    "crewai_run_router_audit", "crewai_run_codebase_research", "crewai_run_test_generation",
    "crewai_run_integration_plan", "crewai_workflow_status", "crewai_workflow_logs",
    "crewai_cancel_workflow",
]


def _route(p):
    return _deterministic_router(p, {}).get("intent")


def setup_function(_fn):
    we.clear()


# ── engine ───────────────────────────────────────────────────────────────────
def test_create_run_completes_with_artifact():
    run = we.create_run("router_audit", "audit the intent router")
    assert run.status == "completed"
    assert run.artifacts and run.findings
    assert we.get_run(run.run_id) is run


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        we.create_run("nope", "x")


def test_waiting_for_input_then_continue():
    run = we.create_run("codebase_research", "research the repo, ask me which module")
    assert run.status == "waiting_for_input"
    done = we.continue_run(run.run_id, "the router")
    assert done.status == "completed" and done.artifacts


def test_cancel():
    run = we.create_run("test_generation", "x")
    # already completed; cancel a fresh waiting one instead
    w = we.create_run("integration_plan", "plan it, ask me the scope")
    assert we.cancel_run(w.run_id).status == "cancelled"


# ── safety proxy ─────────────────────────────────────────────────────────────
def test_proxy_unknown_tool():
    assert proxy.request_tool("definitely_not_a_tool")["status"] == "tool_not_available"


def test_proxy_risky_requires_approval():
    from engine import approval_queue as aq
    aq.clear()
    r = proxy.request_tool("click_ui_element", {"target": "Pay"}, risk="critical", reason="wf")
    assert r["status"] == "waiting_for_approval"
    assert r.get("verified") is not True
    aq.clear()


# ── Nexi tools (via registry) ────────────────────────────────────────────────
def test_tools_registered_and_whitelisted():
    for n in WF_TOOLS:
        assert get_tool(n) is not None, f"{n} not registered"
        assert n in tax.ALLOWED_INTENTS and n in tax.TOOL_INTENTS, f"{n} not whitelisted"


def test_run_router_audit_tool():
    r = execute_tool("crewai_run_router_audit", {})
    assert r["success"] is True and r["verified"] is True
    assert r.get("run_id") and r.get("status") == "completed"


def test_status_and_logs_and_cancel_tools():
    execute_tool("crewai_run_codebase_research", {})
    assert execute_tool("crewai_workflow_status", {})["verified"] is True
    assert isinstance(execute_tool("crewai_workflow_logs", {}).get("logs"), list)
    assert execute_tool("crewai_cancel_workflow", {})["verified"] is True


# ── routing ──────────────────────────────────────────────────────────────────
def test_routing():
    assert _route("run an agent audit of the router") == "crewai_run_router_audit"
    assert _route("research this repo with agents") == "crewai_run_codebase_research"
    assert _route("generate tests with agents") == "crewai_run_test_generation"
    assert _route("workflow status") == "crewai_workflow_status"
    assert _route("cancel workflow") == "crewai_cancel_workflow"


# ── web server route() — stdlib, no dependency, no port binding ───────────────
def test_web_server_routes():
    from engine.integrations.crewai_style import web_server as ws
    assert ws.route("GET", "/health")[1]["ok"] is True
    status, created = ws.route("POST", "/workflows", {"workflow_type": "router_audit", "input": "audit"})
    assert status == 200 and created["status"] == "completed"
    rid = created["run_id"]
    assert ws.route("GET", f"/workflows/{rid}/logs")[1]["logs"]
    assert ws.route("GET", f"/workflows/{rid}/artifacts")[1]["artifacts"]
    assert ws.route("GET", f"/workflows/{rid}")[1]["status"] == "completed"
    assert ws.route("POST", "/workflows", {"workflow_type": "bogus"})[0] == 400
    assert ws.route("GET", "/workflows/nope")[0] == 404
