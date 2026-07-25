"""Nexi Agency Engine — autonomous background workflow engine (clean-room, no external framework).

A workflow run carries a goal, a plan, and flows through agent passes:
  Planner -> Research -> ToolOperator -> Verifier -> Reflection -> Report
Passes are model-ready: with NEXI_AGENCY_AUTONOMY=true they call the Gemini brain; otherwise
they use deterministic stubs (default — safe, offline, test-stable). Runs persist to JSONL so
status/logs survive a restart. Background execution keeps the voice thread free.

ponytail: one file = state + plan + memory + events + runner + agents (pass-functions, not
classes). Real LLM passes are behind a flag with stub fallback; tool use goes through
nexi_tool_proxy + approval. Upgrade a pass to richer reasoning in place — signature is (run, ctx).
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

WORKFLOW_TYPES = {"router_audit", "codebase_research", "test_generation", "integration_plan"}
_TERMINAL = {"completed", "failed", "cancelled"}
_STORE = Path(__file__).resolve().parents[2] / "data" / "nexi" / "agency" / "workflow_runs.jsonl"

# HUD hook — set to a callable(run_id, event_dict). No-op by default.
EVENT_SINK: Callable[[str, dict], None] | None = None


def autonomy_enabled() -> bool:
    return str(os.getenv("NEXI_AGENCY_AUTONOMY", "")).strip().lower() in {"1", "true", "yes", "on"}


def autonomy_mode() -> str:
    # locked | manual | supervised | autonomous_safe
    return (os.getenv("NEXI_AGENCY_MODE", "supervised") or "supervised").strip().lower()


@dataclass
class WorkflowEvent:
    ts: float
    type: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowRun:
    run_id: str
    workflow_type: str
    goal: str
    status: str = "pending"
    mode: str = "supervised"
    created_at: float = 0.0
    updated_at: float = 0.0
    plan: list[str] = field(default_factory=list)
    current_agent: str = ""
    logs: list[str] = field(default_factory=list)
    events: list[WorkflowEvent] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)   # run-local memory
    reflection: str = ""
    result: str | None = None
    waiting_for: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowRun":
        d = dict(d)
        d["events"] = [WorkflowEvent(**e) for e in d.get("events", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class WorkflowDefinition:
    runner: Callable[[WorkflowRun], None]
    continuer: Callable[[WorkflowRun, str], None] | None = None
    canceller: Callable[[WorkflowRun], bool | None] | None = None
    restart_policy: str = "fail"


_RUNS: dict[str, WorkflowRun] = {}
_WORKFLOW_DEFINITIONS: dict[str, WorkflowDefinition] = {}
_LOCK = threading.RLock()
_UNSET = object()


def _now() -> float:
    return time.time()


def _publish_event(run: WorkflowRun, ev: WorkflowEvent) -> None:
    print(f"[NEXI_AGENCY] {run.run_id} {ev.type} {ev.message}", flush=True)
    if EVENT_SINK is not None:
        try:
            EVENT_SINK(run.run_id, asdict(ev))
        except Exception:
            pass


def _emit(run: WorkflowRun, etype: str, message: str, data: dict | None = None) -> None:
    ev = WorkflowEvent(ts=_now(), type=etype, message=message, data=data or {})
    run.events.append(ev)
    run.updated_at = ev.ts
    _publish_event(run, ev)


def _log(run: WorkflowRun, msg: str) -> None:
    run.logs.append(msg)
    run.updated_at = _now()


def _persist(run: WorkflowRun) -> bool:
    try:
        with _LOCK:
            _STORE.parent.mkdir(parents=True, exist_ok=True)
            with _STORE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(run.to_dict()) + "\n")
        return True
    except Exception:
        return False


def checkpoint_run(
    run: WorkflowRun,
    *,
    status: str | None = None,
    current_agent: str | None = None,
    waiting_for: str | None | object = _UNSET,
    result: str | None | object = _UNSET,
    metadata: dict[str, Any] | None = None,
    event_type: str = "",
    message: str = "",
    event_data: dict[str, Any] | None = None,
    expected_statuses: set[str] | None = None,
) -> bool:
    """Update and durably checkpoint a run at a workflow boundary."""
    with _LOCK:
        if expected_statuses is not None and run.status not in expected_statuses:
            return False
        previous = (
            run.status,
            run.current_agent,
            run.waiting_for,
            run.result,
            copy.deepcopy(run.metadata),
            run.updated_at,
            len(run.events),
        )
        if status is not None:
            run.status = status
        if current_agent is not None:
            run.current_agent = current_agent
        if waiting_for is not _UNSET:
            run.waiting_for = waiting_for
        if result is not _UNSET:
            run.result = result
        if metadata:
            run.metadata.update(metadata)
        event = None
        if event_type:
            event = WorkflowEvent(ts=_now(), type=event_type, message=message or event_type, data=event_data or {})
            run.events.append(event)
            run.updated_at = event.ts
        else:
            run.updated_at = _now()
        if _persist(run):
            if event is not None:
                _publish_event(run, event)
            return True
        run.status, run.current_agent, run.waiting_for, run.result = previous[:4]
        run.metadata = previous[4]
        run.updated_at = previous[5]
        del run.events[previous[6]:]
        return False


def register_workflow_type(
    name: str,
    runner: Callable[[WorkflowRun], None],
    *,
    continuer: Callable[[WorkflowRun, str], None] | None = None,
    canceller: Callable[[WorkflowRun], bool | None] | None = None,
    restart_policy: str = "fail",
) -> None:
    """Register an application workflow without coupling it to the built-in passes."""
    workflow_type = str(name or "").strip()
    if not workflow_type or not callable(runner):
        raise ValueError("A workflow name and runner are required.")
    if restart_policy not in {"fail", "pause_for_resume"}:
        raise ValueError("restart_policy must be 'fail' or 'pause_for_resume'.")
    with _LOCK:
        WORKFLOW_TYPES.add(workflow_type)
        _WORKFLOW_DEFINITIONS[workflow_type] = WorkflowDefinition(
            runner,
            continuer,
            canceller,
            restart_policy,
        )
        interrupted = [
            run for run in _RUNS.values()
            if run.workflow_type == workflow_type and run.status in {"pending", "running", "cancelling"}
        ]
    for run in interrupted:
        if restart_policy == "pause_for_resume":
            reconciliation = {
                "code": "interrupted_by_restart",
                "required": True,
                "external_side_effects_replayed": False,
                "message": "The workflow was interrupted. Fresh authorization and repository reconciliation are required.",
            }
            metadata_update: dict[str, Any] = {"restart_reconciliation": reconciliation}
            studio = copy.deepcopy(run.metadata.get("studio") or {})
            if studio:
                stage = str(studio.get("current_stage") or studio.get("stage") or "")
                for gate in (studio.get("gates") or {}).values():
                    if gate.get("stage") == stage:
                        gate.update({"state": "BLOCKED", "status": "BLOCKED", "reason": "restart_reconciliation_required"})
                        break
                studio["blocker"] = {
                    "stage": stage,
                    "reason": "restart_reconciliation_required",
                    "questions": [reconciliation["message"]],
                }
                studio["status"] = "waiting_for_input"
                metadata_update["studio"] = studio
            checkpoint_run(
                run,
                status="waiting_for_input",
                current_agent="",
                waiting_for=reconciliation["message"],
                result=reconciliation["message"],
                metadata=metadata_update,
                event_type="workflow_paused_for_reconciliation",
                message=reconciliation["message"],
                event_data=reconciliation,
                expected_statuses={"pending", "running", "cancelling"},
            )
            continue
        failure = {"code": "interrupted_by_restart", "message": "The workflow was interrupted by a restart."}
        checkpoint_run(
            run,
            status="failed",
            current_agent="",
            result=failure["message"],
            metadata={"failure": failure},
            event_type="workflow_failed",
            message=failure["message"],
            event_data=failure,
            expected_statuses={"pending", "running", "cancelling"},
        )


def _load() -> None:
    """Restore the latest valid snapshot for every run from the complete JSONL."""
    try:
        if not _STORE.exists():
            return
        latest: dict[str, WorkflowRun] = {}
        with _STORE.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    run = WorkflowRun.from_dict(json.loads(line))
                    latest[run.run_id] = run
                except Exception:
                    continue
        with _LOCK:
            _RUNS.update(latest)
    except Exception:
        pass


# ── Model hook (real behind flag, stub by default) ───────────────────────────
# Optional backend hook. Core stays backend-agnostic (clean-room, no framework
# knowledge here); a plugin may register an override via set_model_override().
_model_override = None


def set_model_override(fn):
    """Register an optional model backend: fn(role, prompt) -> str ('' to skip)."""
    global _model_override
    _model_override = fn


def _model(role: str, prompt: str) -> str:
    if not autonomy_enabled():
        return ""
    if _model_override is not None:
        try:
            out = _model_override(role, prompt)
            if out:
                return out
        except Exception:
            pass
    try:  # default: best-effort Gemini brain; any failure -> stub
        from engine.gemini_brain import ask_gemini  # type: ignore
        return str(ask_gemini(f"You are Nexi's {role}. {prompt}") or "")
    except Exception:
        return ""


# ── Agent passes ─────────────────────────────────────────────────────────────
def _agent(run: WorkflowRun, name: str, note: str) -> None:
    run.current_agent = name
    _emit(run, "agent_started", f"{name}", {"agent": name})
    _log(run, f"{name}: {note}")


def _plan(run: WorkflowRun) -> None:
    _agent(run, "PlannerAgent", "building a plan")
    model = _model("planner", f"Goal: {run.goal}. List 3-5 concise steps to achieve it.")
    if model:
        run.plan = [s.strip("-* ").strip() for s in model.splitlines() if s.strip()][:5]
    if not run.plan:  # stub
        run.plan = [
            f"Clarify the goal: {run.goal}",
            "Gather relevant context/evidence",
            "Decide if any tool is needed (via safety proxy)",
            "Verify findings against the goal",
            "Write a concise report",
        ]
    _emit(run, "plan_created", f"{len(run.plan)} steps", {"plan": run.plan})


def _research(run: WorkflowRun) -> None:
    _agent(run, "ResearchAgent", "gathering context")
    model = _model("researcher", f"Goal: {run.goal}. Summarize key findings in 2-3 bullets.")
    run.findings.append(model.strip() if model else f"Context gathered for: {run.goal}")


def _tool_step(run: WorkflowRun) -> None:
    _agent(run, "ToolOperatorAgent", "deciding tool use")
    # Background workflows are analysis-first; no tool requested by default. When a pass needs
    # one it MUST go through nexi_tool_proxy (risk + approval enforced) — never direct control.
    _log(run, "No tool required for this step (analysis only).")
    _emit(run, "tool_decision", "no tool needed")


def _verify(run: WorkflowRun) -> None:
    _agent(run, "VerifierAgent", "checking findings")
    ok = bool(run.findings)
    _emit(run, "verification_passed" if ok else "verification_failed", "evidence present" if ok else "no evidence")
    if not ok:
        run.findings.append("Verifier: no evidence gathered.")


def _reflect(run: WorkflowRun) -> None:
    _agent(run, "ReflectionAgent", "writing a lesson")
    model = _model("reflection", f"Goal: {run.goal}. One lesson for next time.")
    run.reflection = model.strip() if model else f"Lesson: keep the plan for '{run.workflow_type}' tight and evidence-backed."


def _report_body(run: WorkflowRun) -> str:
    lines = [f"# {run.workflow_type} report", "", f"Goal: {run.goal}", "", "## Plan"]
    lines += [f"{i + 1}. {s}" for i, s in enumerate(run.plan)] or ["(none)"]
    lines += ["", "## Findings"] + ([f"- {f}" for f in run.findings] or ["- (none)"])
    lines += ["", "## Reflection", run.reflection or "(none)"]
    lines += ["", f"_Nexi Agency Engine · mode={run.mode} · autonomy={'on' if autonomy_enabled() else 'stub'}_"]
    return "\n".join(lines)


def _finish(run: WorkflowRun) -> None:
    run.status = "running"
    _research(run)
    _tool_step(run)
    _verify(run)
    _reflect(run)
    _agent(run, "ReportAgent", "writing the report")
    run.artifacts.append({"name": f"{run.workflow_type}_report", "content_type": "text/markdown",
                          "created_at": _now(), "body": _report_body(run)})
    _emit(run, "artifact_created", f"{run.workflow_type}_report")
    run.result = f"{run.workflow_type} completed: {len(run.findings)} findings, {len(run.plan)}-step plan."
    run.status = "completed"
    run.current_agent = ""
    _emit(run, "workflow_completed", run.result)
    _persist(run)


def _requests_user_input(goal: str) -> bool:
    clauses = [part.strip().lower() for part in re.split(r"[,;.!?]", str(goal or ""))]
    return any(
        clause in {"ask me", "please ask me", "need user", "need more"}
        or clause.startswith(("ask me ", "please ask me ", "need user input", "need more input",
                              "need more context", "need more details"))
        for clause in clauses
    )


def _run_passes(run: WorkflowRun) -> None:
    run.status = "running"
    _emit(run, "workflow_started", f"{run.workflow_type}: {run.goal}")
    _plan(run)
    if _requests_user_input(run.goal):
        run.status = "waiting_for_input"
        run.waiting_for = "additional_user_context"
        _emit(run, "human_input_required", "need more detail")
        _persist(run)
        return
    _finish(run)


def _run_registered(run: WorkflowRun, definition: WorkflowDefinition, *, resumed: bool = False) -> None:
    if not checkpoint_run(
        run,
        status="running",
        current_agent="",
        waiting_for=None,
        event_type="workflow_resumed" if resumed else "workflow_started",
        message=f"{run.workflow_type}: {run.goal}",
        expected_statuses={"pending"},
    ):
        return
    try:
        definition.runner(run)
    except Exception as exc:
        failure = {"code": "runner_exception", "message": f"{type(exc).__name__}: {exc}"}
        checkpoint_run(
            run,
            status="failed",
            current_agent="",
            result=failure["message"],
            metadata={"failure": failure},
            event_type="workflow_failed",
            message=failure["message"],
            event_data=failure,
            expected_statuses={"running"},
        )
        return
    if run.status == "running":
        failure = {"code": "runner_incomplete", "message": "The workflow runner exited without a terminal state."}
        checkpoint_run(
            run,
            status="failed",
            current_agent="",
            result=failure["message"],
            metadata={"failure": failure},
            event_type="workflow_failed",
            message=failure["message"],
            event_data=failure,
            expected_statuses={"running"},
        )


# ── Public API ───────────────────────────────────────────────────────────────
def create_run(
    workflow_type: str,
    goal: str,
    background: bool = False,
    *,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> WorkflowRun:
    wtype = (workflow_type or "").strip()
    if wtype not in WORKFLOW_TYPES:
        raise ValueError(f"Unsupported workflow_type: {wtype!r} (allowed: {sorted(WORKFLOW_TYPES)})")
    selected_run_id = str(run_id or f"wf_{uuid.uuid4().hex[:12]}").strip()
    if not selected_run_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in selected_run_id):
        raise ValueError("Invalid workflow run ID.")
    run = WorkflowRun(run_id=selected_run_id, workflow_type=wtype,
                      goal=str(goal or "").strip(), mode=autonomy_mode(),
                      created_at=_now(), updated_at=_now(), metadata=dict(metadata or {}))
    with _LOCK:
        if run.run_id in _RUNS:
            raise ValueError(f"Workflow run already exists: {run.run_id}")
        _RUNS[run.run_id] = run
    if not _persist(run):
        with _LOCK:
            _RUNS.pop(run.run_id, None)
        raise RuntimeError("Could not persist the workflow run.")
    definition = _WORKFLOW_DEFINITIONS.get(wtype)
    target = (lambda: _run_registered(run, definition)) if definition else (lambda: _run_passes(run))
    if background:
        threading.Thread(target=target, daemon=True).start()
    else:
        target()
    return run


def get_run(run_id: str) -> WorkflowRun | None:
    with _LOCK:
        return _RUNS.get(run_id)


def list_runs() -> list[WorkflowRun]:
    with _LOCK:
        return list(_RUNS.values())


def latest_run() -> WorkflowRun | None:
    with _LOCK:
        return max(_RUNS.values(), key=lambda r: r.created_at) if _RUNS else None


def current_activity() -> dict[str, Any]:
    run = latest_run()
    if not run:
        return {"active": False}
    last = run.events[-1].type if run.events else ""
    return {"active": run.status not in _TERMINAL, "run_id": run.run_id, "workflow_type": run.workflow_type,
            "status": run.status, "current_agent": run.current_agent, "last_event": last,
            "plan_steps": len(run.plan), "findings": len(run.findings), "mode": run.mode}


def cancel_run(run_id: str) -> WorkflowRun | None:
    with _LOCK:
        run = _RUNS.get(run_id)
        definition = _WORKFLOW_DEFINITIONS.get(run.workflow_type) if run else None
        if not run or run.status in _TERMINAL:
            return run
        if run.status == "cancelling":
            requested = True
        else:
            requested = checkpoint_run(
                run,
                status="cancelling",
                current_agent="",
                metadata={"cancel_requested": True},
                event_type="workflow_cancelling",
                message="cancellation requested by user",
                expected_statuses={"pending", "running", "waiting_for_input"},
            )
    if not requested:
        return run
    stopped = True
    if definition and definition.canceller:
        try:
            stopped = definition.canceller(run) is not False
        except Exception:
            stopped = False
    if stopped:
        checkpoint_run(
            run,
            status="cancelled",
            current_agent="",
            metadata={"cancel_failed": False},
            event_type="workflow_cancelled",
            message="cancelled by user",
            expected_statuses={"cancelling"},
        )
    else:
        checkpoint_run(
            run,
            status="cancelling",
            metadata={"cancel_failed": True},
            event_type="workflow_cancel_failed",
            message="Cancellation was requested but process termination was not confirmed.",
            expected_statuses={"cancelling"},
        )
    return run


def continue_run(run_id: str, user_input: str) -> WorkflowRun | None:
    with _LOCK:
        run = _RUNS.get(run_id)
        definition = _WORKFLOW_DEFINITIONS.get(run.workflow_type) if run else None
        if not run or run.status != "waiting_for_input":
            return run
        if definition:
            previous_metadata = copy.deepcopy(run.metadata)
            if definition.continuer:
                definition.continuer(run, str(user_input or "").strip())
            resumed = checkpoint_run(
                run,
                status="pending",
                current_agent="",
                waiting_for=None,
                event_type="human_input_received",
                message="got it",
                expected_statuses={"waiting_for_input"},
            )
            if not resumed:
                run.metadata = previous_metadata
        else:
            resumed = False
    if definition:
        if not resumed:
            return run
        threading.Thread(
            target=_run_registered,
            args=(run, definition),
            kwargs={"resumed": True},
            daemon=True,
        ).start()
        return run
    run.status = "running"
    run.waiting_for = None
    run.goal = f"{run.goal} | {user_input}".strip(" |")
    _emit(run, "human_input_received", "got it", {"user_input": user_input})
    run.findings.clear()
    _finish(run)
    return run


def clear() -> None:
    with _LOCK:
        _RUNS.clear()


_load()  # restore prior runs so status/logs survive a restart


if __name__ == "__main__":
    clear()
    r = create_run("router_audit", "audit the intent router")
    assert r.status == "completed" and r.plan and r.artifacts and r.reflection, r
    w = create_run("codebase_research", "research the repo, ask me which module")
    assert w.status == "waiting_for_input"
    assert continue_run(w.run_id, "the router").status == "completed"
    assert current_activity()["run_id"]
    try:
        create_run("bogus", "x"); assert False
    except ValueError:
        pass
    print("OK", len(list_runs()), "runs; mode=", autonomy_mode())
