import sys
import os
import time
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine.agency import workflow_engine as we
from engine.agency import nexi_tool_proxy as proxy


WF_TOOLS = [
    "nexi_run_router_audit", "nexi_run_codebase_research", "nexi_run_test_generation",
    "nexi_run_integration_plan", "nexi_workflow_status", "nexi_agent_activity",
    "nexi_workflow_logs", "nexi_workflow_artifacts", "nexi_cancel_workflow", "nexi_continue_workflow",
]


def _route(p):
    return _deterministic_router(p, {}).get("intent")


def setup_function(_fn):
    we.clear()


@pytest.fixture(autouse=True)
def _tmp_store(monkeypatch, tmp_path):
    monkeypatch.setattr(we, "_STORE", tmp_path / "workflow_runs.jsonl")
    monkeypatch.setenv("NEXI_AGENCY_AUTONOMY", "false")


# ── engine: real plan + agents + reflection ───────────────────────────────────
def test_run_produces_plan_findings_reflection_artifact():
    run = we.create_run("router_audit", "audit the intent router")
    assert run.status == "completed"
    assert run.plan and run.findings and run.reflection and run.artifacts
    # the report includes the plan + reflection
    body = run.artifacts[0]["body"]
    assert "## Plan" in body and "## Reflection" in body


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        we.create_run("nope", "x")


def test_waiting_then_continue():
    run = we.create_run("codebase_research", "research, ask me which module")
    assert run.status == "waiting_for_input"
    assert we.continue_run(run.run_id, "the router").status == "completed"


@pytest.mark.parametrize("goal", ["ask me", "please ask me", "need user input"])
def test_explicit_user_input_request_waits(goal):
    assert we.create_run("codebase_research", goal).status == "waiting_for_input"


@pytest.mark.parametrize("goal", [
    "research how to handle the phrase ask me without pausing",
    "audit code that says do not ask me for input",
    "investigate why a task says need more memory",
])
def test_workflow_waiting_does_not_use_naive_substring_matches(goal):
    run = we.create_run("codebase_research", goal)
    assert run.status == "completed"
    assert run.waiting_for is None


def test_background_execution_completes():
    run = we.create_run("router_audit", "x", background=True)
    for _ in range(100):
        if we.get_run(run.run_id).status in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert we.get_run(run.run_id).status == "completed"


def test_persistence_writes_jsonl():
    we.create_run("router_audit", "persist me")
    assert we._STORE.exists() and we._STORE.read_text(encoding="utf-8").strip()


def test_current_activity():
    we.create_run("router_audit", "x")
    act = we.current_activity()
    assert act["run_id"] and act["status"] == "completed"


# ── safety proxy + autonomy modes ─────────────────────────────────────────────
def test_proxy_unknown_tool():
    assert proxy.request_tool("definitely_not_a_tool")["status"] == "tool_not_available"


def test_proxy_risky_requires_approval():
    from engine import approval_queue as aq
    aq.clear()
    r = proxy.request_tool("click_ui_element", {"target": "Pay"}, risk="critical", reason="wf")
    assert r["status"] == "waiting_for_approval" and r.get("verified") is not True
    aq.clear()


def test_proxy_locked_mode_refuses(monkeypatch):
    monkeypatch.setenv("NEXI_AGENCY_MODE", "locked")
    r = proxy.request_tool("get_battery_status", {}, risk="low")
    assert r["status"] == "rejected"


def test_proxy_execution_exception_returns_structured_error(monkeypatch):
    import engine.tool_registry as registry

    monkeypatch.setattr(registry, "get_tool", lambda _name: object())
    monkeypatch.setattr(registry, "execute_tool", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("tool crashed")))

    result = proxy.request_tool("broken_tool")

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "tool_execution_failed",
        "type": "RuntimeError",
        "message": "tool crashed",
    }


def test_proxy_registry_lookup_exception_returns_structured_error(monkeypatch):
    import engine.tool_registry as registry

    monkeypatch.setattr(registry, "get_tool", lambda _name: (_ for _ in ()).throw(RuntimeError("registry corrupted")))

    result = proxy.request_tool("broken_tool")

    assert result["success"] is False
    assert result["status"] == "tool_not_available"
    assert result["error"]["code"] == "tool_registry_unavailable"
    assert result["error"]["type"] == "RuntimeError"


def test_proxy_approval_gate_empty_response_fails_closed(monkeypatch):
    import engine.approval_queue as approval_queue
    import engine.tool_registry as registry

    monkeypatch.setattr(registry, "get_tool", lambda _name: object())
    monkeypatch.setattr(approval_queue, "gate", lambda *_a, **_k: None)
    monkeypatch.setattr(registry, "execute_tool", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not execute")))

    result = proxy.request_tool("risky_tool", risk="critical")

    assert result["success"] is False
    assert result["status"] == "rejected"
    assert result["error"]["code"] == "approval_not_recorded"


def test_crewai_failure_is_logged(monkeypatch, caplog):
    from engine.agency import crewai_adapter

    class BrokenAgent:
        def __init__(self, **_kwargs):
            raise RuntimeError("CrewAI boot failed")

    fake = types.SimpleNamespace(Agent=BrokenAgent, Task=object, Crew=object)
    monkeypatch.setitem(sys.modules, "crewai", fake)

    with caplog.at_level("ERROR"):
        result = crewai_adapter.run_role("researcher", "find evidence")

    assert result == ""
    assert "CrewAI role researcher failed" in caplog.text
    assert "CrewAI boot failed" in caplog.text


# ── Nexi tools (via registry) ─────────────────────────────────────────────────
def test_tools_registered_and_whitelisted():
    for n in WF_TOOLS:
        assert get_tool(n) is not None, f"{n} not registered"
        assert n in tax.ALLOWED_INTENTS and n in tax.TOOL_INTENTS, f"{n} not whitelisted"


def test_run_tool_completes_and_has_no_crewai_branding():
    r = execute_tool("nexi_run_router_audit", {})
    assert r["success"] is True and r["verified"] is True and r.get("run_id")
    assert "crewai" not in r["message"].lower()


def test_status_activity_logs_artifacts_cancel():
    execute_tool("nexi_run_codebase_research", {})
    assert execute_tool("nexi_workflow_status", {})["verified"] is True
    assert execute_tool("nexi_agent_activity", {})["verified"] is True
    assert isinstance(execute_tool("nexi_workflow_logs", {}).get("logs"), list)
    assert execute_tool("nexi_workflow_artifacts", {}).get("artifacts")
    assert execute_tool("nexi_cancel_workflow", {})["verified"] is True


# ── routing ───────────────────────────────────────────────────────────────────
def test_routing():
    assert _route("start an agent audit of the intent router") == "nexi_run_router_audit"
    assert _route("research this repo with agents") == "nexi_run_codebase_research"
    assert _route("show current agent activity") == "nexi_agent_activity"
    assert _route("workflow status") == "nexi_workflow_status"
    assert _route("show the agent report") == "nexi_workflow_artifacts"
    assert _route("cancel workflow") == "nexi_cancel_workflow"


# ── web server route() (stdlib, no port binding) ──────────────────────────────
def test_web_server_routes():
    from engine.agency import web_server as ws
    assert ws.route("GET", "/health")[1]["ok"] is True
    status, created = ws.route("POST", "/workflows", {"workflow_type": "router_audit", "input": "audit"})
    assert status == 200 and created["status"] == "completed"
    rid = created["run_id"]
    assert ws.route("GET", f"/workflows/{rid}/logs")[1]["logs"]
    assert ws.route("POST", "/workflows", {"workflow_type": "bogus"})[0] == 400
    assert ws.route("GET", "/workflows/nope")[0] == 404

    studio = we.WorkflowRun(
        run_id="wf_abcdef123456",
        workflow_type="studio_build",
        goal="test",
        status="waiting_for_input",
        created_at=time.time(),
    )
    we._RUNS[studio.run_id] = studio
    assert ws.route("POST", f"/workflows/{studio.run_id}/continue", {"user_input": "bypass"})[0] == 403
    assert ws.route("POST", f"/workflows/{studio.run_id}/cancel")[0] == 403


def test_web_server_requires_token_and_loopback(monkeypatch):
    from engine.agency import web_server as ws
    monkeypatch.delenv("NEXI_AGENCY_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        ws.serve()
    monkeypatch.setenv("NEXI_AGENCY_API_TOKEN", "test-token")
    with pytest.raises(ValueError):
        ws.serve(host="0.0.0.0")


def test_no_crewai_in_engine_source():
    import pathlib
    src = pathlib.Path(we.__file__).read_text(encoding="utf-8").lower()
    assert "crewai" not in src
