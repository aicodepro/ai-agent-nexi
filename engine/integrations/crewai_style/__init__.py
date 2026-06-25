"""Clean-room CrewAI-style workflow plugin for Nexi (isolated, no CrewAI source).

Exposes background multi-agent workflows as Nexi tools. Live fast-path commands stay in the
normal router; these are for big jobs (audit/research/test-plan/integration). All tools are
read-only/low-risk wrappers around workflow_engine; any real tool use by agents goes through
nexi_tool_proxy -> approval gate.
"""

from __future__ import annotations

from typing import Any

from engine.integrations.crewai_style import workflow_engine as _we
from engine.integrations.crewai_style.nexi_tool_proxy import request_tool  # re-export

__all__ = ["request_tool", "workflow_engine"]
workflow_engine = _we


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "crewai_style"), "message": message, **extra}


def _run(wtype: str, tool: str, slots: dict | None) -> dict[str, Any]:
    text = str((slots or {}).get("input") or (slots or {}).get("text") or wtype.replace("_", " ")).strip()
    try:
        run = _we.create_run(wtype, text)
    except Exception as exc:
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": tool,
                "message": f"Couldn't start that workflow: {exc}"}
    if run.status == "waiting_for_input":
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": tool,
                "expects_user_reply": True, "run_id": run.run_id,
                "message": f"Starting the {wtype.replace('_', ' ')} workflow — what should I focus on?"}
    return _ok(f"{wtype.replace('_', ' ').capitalize()} workflow {run.run_id} done — {run.result} Ask for 'workflow logs' for detail.",
               tool=tool, run_id=run.run_id, status=run.status, artifacts=len(run.artifacts), findings=len(run.findings))


def crewai_run_router_audit(slots: dict | None = None) -> dict[str, Any]:
    return _run("router_audit", "crewai_run_router_audit", slots)


def crewai_run_codebase_research(slots: dict | None = None) -> dict[str, Any]:
    return _run("codebase_research", "crewai_run_codebase_research", slots)


def crewai_run_test_generation(slots: dict | None = None) -> dict[str, Any]:
    return _run("test_generation", "crewai_run_test_generation", slots)


def crewai_run_integration_plan(slots: dict | None = None) -> dict[str, Any]:
    return _run("integration_plan", "crewai_run_integration_plan", slots)


def _resolve(slots: dict | None):
    rid = str((slots or {}).get("run_id") or "").strip()
    return _we.get_run(rid) if rid else _we.latest_run()


def crewai_workflow_status(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run:
        return _ok("There are no workflows yet.", tool="crewai_workflow_status", count=0)
    return _ok(f"Workflow {run.run_id} ({run.workflow_type}): {run.status}, {len(run.findings)} findings, {len(run.artifacts)} artifacts.",
               tool="crewai_workflow_status", run_id=run.run_id, status=run.status,
               workflow_type=run.workflow_type, artifacts=len(run.artifacts))


def crewai_workflow_logs(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run:
        return _ok("No workflow logs yet.", tool="crewai_workflow_logs", logs=[])
    tail = run.logs[-8:]
    return _ok(f"Last {len(tail)} log line(s) for {run.run_id}: " + " | ".join(tail),
               tool="crewai_workflow_logs", run_id=run.run_id, logs=run.logs)


def crewai_cancel_workflow(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run:
        return _ok("There's no workflow to cancel.", tool="crewai_cancel_workflow")
    run = _we.cancel_run(run.run_id)
    return _ok(f"Workflow {run.run_id} is now {run.status}.", tool="crewai_cancel_workflow",
               run_id=run.run_id, status=run.status)
