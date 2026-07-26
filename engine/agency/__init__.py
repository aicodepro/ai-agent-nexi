"""Nexi Agency Engine — autonomous background workflows exposed as Nexi tools.

Live fast-path commands stay in the normal router; these handle big jobs (audit/research/
test-plan/integration). Runs go through the planner->research->tool->verify->reflect->report
loop. Tool use by agents goes through nexi_tool_proxy -> approval gate. Clean-room core with
no framework baked in; an optional CrewAI backend can be enabled via NEXI_AGENCY_BACKEND=crewai.
"""

from __future__ import annotations

from typing import Any

from engine.agency import workflow_engine as _we
from engine.agency.nexi_tool_proxy import request_tool  # re-export

# Plug in the optional CrewAI backend hook (dormant unless enabled + installed).
try:
    from engine.agency import crewai_adapter as _crewai_adapter
    _crewai_adapter.register()
except Exception:
    pass

__all__ = ["request_tool", "workflow_engine"]
workflow_engine = _we


def _studio_module(*, register: bool = True):
    """Import and register Studio only when a Studio handler is invoked."""
    from engine.studio import supervisor
    if register:
        supervisor.register()
    return supervisor


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "nexi_agency"), "message": message, **extra}


def _accepted(message: str, **extra: Any) -> dict[str, Any]:
    """A workflow was STARTED. Nothing has been verified yet.

    Starting is not completing. _ok() hardcodes verified=True, and the
    background branch used it for a run whose agents had not executed - the live
    trace emitted `verified=true` and `[TOOL] success` before PlannerAgent even
    started, then the planner/research/report agents ran afterwards. The
    verified flag is what downstream treats as evidence of a real outcome, so a
    start must never set it.

    The wording must also avoid reading as a completion claim: the unverified-
    action guard rewrites any message matching "Started ...", which is correct
    behaviour once verified=False.
    """
    return {"handled": True, "ok": True, "success": True, "verified": False,
            "tool": extra.pop("tool", "nexi_agency"), "message": message, **extra}


# Only these run statuses count as a verified terminal success.
_TERMINAL_SUCCESS = frozenset({"completed", "complete", "done", "success", "succeeded"})


def _run(wtype: str, tool: str, slots: dict | None) -> dict[str, Any]:
    goal = str((slots or {}).get("goal") or (slots or {}).get("input") or (slots or {}).get("text") or wtype.replace("_", " ")).strip()
    background = _we.autonomy_enabled()
    try:
        run = _we.create_run(wtype, goal, background=background)
    except Exception as exc:
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": tool,
                "message": f"Couldn't start that workflow: {exc}"}
    if run.status == "waiting_for_input":
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": tool,
                "expects_user_reply": True, "run_id": run.run_id,
                "message": f"Starting the {wtype.replace('_', ' ')} workflow — what should I focus on?"}
    label = wtype.replace("_", " ")
    if background:  # autonomous: return immediately, work continues in the background
        return _accepted(
            f"I've begun the {label} workflow in the background ({run.run_id}). "
            f"I'll report the result once it finishes and is verified — "
            f"ask for agent activity or logs anytime.",
            tool=tool, run_id=run.run_id, status=run.status, job_state="RUNNING")

    # Synchronous run: only a terminal-successful run is a verified outcome.
    if str(run.status or "").strip().lower() not in _TERMINAL_SUCCESS:
        return _accepted(
            f"The {label} workflow {run.run_id} ended with status {run.status}. "
            f"Ask for the agent logs for detail.",
            tool=tool, run_id=run.run_id, status=run.status, job_state=str(run.status or "").upper())
    return _ok(f"{label.capitalize()} agent workflow {run.run_id} done — {run.result} "
               f"Ask for the agent report for detail.",
               tool=tool, run_id=run.run_id, status=run.status, job_state="COMPLETED",
               plan_steps=len(run.plan), artifacts=len(run.artifacts))


def nexi_run_router_audit(slots: dict | None = None) -> dict[str, Any]:
    return _run("router_audit", "nexi_run_router_audit", slots)


def nexi_run_codebase_research(slots: dict | None = None) -> dict[str, Any]:
    return _run("codebase_research", "nexi_run_codebase_research", slots)


def nexi_run_test_generation(slots: dict | None = None) -> dict[str, Any]:
    return _run("test_generation", "nexi_run_test_generation", slots)


def nexi_run_integration_plan(slots: dict | None = None) -> dict[str, Any]:
    return _run("integration_plan", "nexi_run_integration_plan", slots)


def _resolve(slots: dict | None):
    rid = str((slots or {}).get("run_id") or "").strip()
    return _we.get_run(rid) if rid else _we.latest_run()


def nexi_workflow_status(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run:
        return _ok("There are no agent workflows yet.", tool="nexi_workflow_status", count=0)
    return _ok(f"Workflow {run.run_id} ({run.workflow_type}): {run.status}, agent {run.current_agent or 'idle'}, "
               f"{len(run.plan)}-step plan, {len(run.findings)} findings, {len(run.artifacts)} artifacts.",
               tool="nexi_workflow_status", run_id=run.run_id, status=run.status, workflow_type=run.workflow_type)


def nexi_agent_activity(slots: dict | None = None) -> dict[str, Any]:
    act = _we.current_activity()
    if not act.get("run_id"):
        return _ok("No agent activity right now.", tool="nexi_agent_activity", **act)
    msg = (f"Agent activity: {act['workflow_type']} is {act['status']}, "
           f"current agent {act['current_agent'] or 'idle'}, last event {act['last_event'] or 'none'} "
           f"({act['plan_steps']}-step plan).")
    return _ok(msg, tool="nexi_agent_activity", **act)


def nexi_workflow_logs(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run:
        return _ok("No agent logs yet.", tool="nexi_workflow_logs", logs=[])
    tail = run.logs[-8:]
    return _ok(f"Last {len(tail)} log line(s) for {run.run_id}: " + " | ".join(tail),
               tool="nexi_workflow_logs", run_id=run.run_id, logs=run.logs)


def nexi_workflow_artifacts(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    arts = run.artifacts if run else []
    if not arts:
        return _ok("No agent reports yet.", tool="nexi_workflow_artifacts", artifacts=[])
    names = ", ".join(a.get("name", "?") for a in arts)
    return _ok(f"{len(arts)} agent report(s) for {run.run_id}: {names}.",
               tool="nexi_workflow_artifacts", run_id=run.run_id, artifacts=arts)


def nexi_cancel_workflow(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run:
        return _ok("There's no agent workflow to cancel.", tool="nexi_cancel_workflow")
    if run.workflow_type == "studio_build":
        return {"handled": True, "ok": False, "success": False, "verified": False,
                "tool": "nexi_cancel_workflow", "message": "Use an explicit 'cancel studio' command to cancel a Studio build."}
    run = _we.cancel_run(run.run_id)
    return _ok(f"Workflow {run.run_id} is now {run.status}.", tool="nexi_cancel_workflow",
               run_id=run.run_id, status=run.status)


def nexi_continue_workflow(slots: dict | None = None) -> dict[str, Any]:
    run = _resolve(slots)
    if not run or run.status != "waiting_for_input":
        return _ok("There's no paused agent workflow to continue.", tool="nexi_continue_workflow",
                   status=(run.status if run else "none"))
    if run.workflow_type == "studio_build":
        return {"handled": True, "ok": False, "success": False, "verified": False,
                "tool": "nexi_continue_workflow", "message": "Use an explicit 'studio continue: ...' command to resume a Studio build."}
    answer = str((slots or {}).get("input") or (slots or {}).get("text") or "").strip()
    run = _we.continue_run(run.run_id, answer)
    return _ok(f"Resumed workflow {run.run_id} — {run.result or run.status}.",
               tool="nexi_continue_workflow", run_id=run.run_id, status=run.status)


def nexi_start_studio_build(slots: dict | None = None) -> dict[str, Any]:
    return _studio_module().start_studio_build(slots)


def nexi_studio_status(slots: dict | None = None) -> dict[str, Any]:
    return _studio_module(register=False).studio_status(slots)


def nexi_cancel_studio_build(slots: dict | None = None) -> dict[str, Any]:
    return _studio_module().cancel_studio_build(slots)


def nexi_continue_studio_build(slots: dict | None = None) -> dict[str, Any]:
    return _studio_module().continue_studio_build(slots)
