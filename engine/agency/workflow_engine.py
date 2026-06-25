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

import json
import os
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowRun":
        d = dict(d)
        d["events"] = [WorkflowEvent(**e) for e in d.get("events", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


_RUNS: dict[str, WorkflowRun] = {}


def _now() -> float:
    return time.time()


def _emit(run: WorkflowRun, etype: str, message: str, data: dict | None = None) -> None:
    ev = WorkflowEvent(ts=_now(), type=etype, message=message, data=data or {})
    run.events.append(ev)
    run.updated_at = ev.ts
    print(f"[NEXI_AGENCY] {run.run_id} {etype} {message}", flush=True)
    if EVENT_SINK is not None:
        try:
            EVENT_SINK(run.run_id, asdict(ev))
        except Exception:
            pass


def _log(run: WorkflowRun, msg: str) -> None:
    run.logs.append(msg)
    run.updated_at = _now()


def _persist(run: WorkflowRun) -> None:
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with _STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(run.to_dict()) + "\n")
    except Exception:
        pass


def _load(limit: int = 50) -> None:
    try:
        if not _STORE.exists():
            return
        for line in _STORE.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                run = WorkflowRun.from_dict(json.loads(line))
                _RUNS[run.run_id] = run  # last snapshot wins
            except Exception:
                continue
    except Exception:
        pass


# ── Model hook (real behind flag, stub by default) ───────────────────────────
def _model(role: str, prompt: str) -> str:
    if not autonomy_enabled():
        return ""
    try:  # best-effort Gemini brain; any failure -> stub
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


def _run_passes(run: WorkflowRun) -> None:
    run.status = "running"
    _emit(run, "workflow_started", f"{run.workflow_type}: {run.goal}")
    _plan(run)
    if any(p in run.goal.lower() for p in ("ask me", "need user", "need more")):
        run.status = "waiting_for_input"
        run.waiting_for = "additional_user_context"
        _emit(run, "human_input_required", "need more detail")
        _persist(run)
        return
    _finish(run)


# ── Public API ───────────────────────────────────────────────────────────────
def create_run(workflow_type: str, goal: str, background: bool = False) -> WorkflowRun:
    wtype = (workflow_type or "").strip()
    if wtype not in WORKFLOW_TYPES:
        raise ValueError(f"Unsupported workflow_type: {wtype!r} (allowed: {sorted(WORKFLOW_TYPES)})")
    run = WorkflowRun(run_id=f"wf_{uuid.uuid4().hex[:12]}", workflow_type=wtype,
                      goal=str(goal or "").strip(), mode=autonomy_mode(),
                      created_at=_now(), updated_at=_now())
    _RUNS[run.run_id] = run
    if background:
        threading.Thread(target=_run_passes, args=(run,), daemon=True).start()
    else:
        _run_passes(run)
    return run


def get_run(run_id: str) -> WorkflowRun | None:
    return _RUNS.get(run_id)


def list_runs() -> list[WorkflowRun]:
    return list(_RUNS.values())


def latest_run() -> WorkflowRun | None:
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
    run = _RUNS.get(run_id)
    if run and run.status not in _TERMINAL:
        run.status = "cancelled"
        _emit(run, "workflow_cancelled", "cancelled by user")
        _persist(run)
    return run


def continue_run(run_id: str, user_input: str) -> WorkflowRun | None:
    run = _RUNS.get(run_id)
    if not run or run.status != "waiting_for_input":
        return run
    run.status = "running"
    run.waiting_for = None
    run.goal = f"{run.goal} | {user_input}".strip(" |")
    _emit(run, "human_input_received", "got it", {"user_input": user_input})
    run.findings.clear()
    _finish(run)
    return run


def clear() -> None:
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
