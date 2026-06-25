"""Clean-room CrewAI-style background workflow engine for Nexi.

Original code — NO CrewAI source copied. Concepts only (Agents/Tasks/Crew/Events).
In-memory, stdlib-only, synchronous. Runs a fixed multi-agent "crew" pass that produces
a markdown report artifact. Used for BACKGROUND jobs (audit/research/test-plan/integration),
never the live voice fast-path.

ponytail: one file = models + state + workflow-memory + events + runner + agents. The spec
listed these as separate files; they are speculative at this size. Split when a second
consumer needs one in isolation. Agents are pass-functions, not 6 classes — upgrade a pass
to a real LLM call (Groq/Gemini) in-place when needed; signature already takes (run, ctx).
Synchronous because passes are instant placeholders; move to a thread when a pass does real IO.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

WORKFLOW_TYPES = {"router_audit", "codebase_research", "test_generation", "integration_plan"}
_TERMINAL = {"completed", "failed", "cancelled"}

# ponytail: single optional sink instead of a pub/sub event bus. HUD sets this to a callable
# (run_id, event_dict). Defaults to no-op so nothing breaks when HUD isn't wired.
EVENT_SINK: Callable[[str, dict], None] | None = None


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
    input: str
    status: str = "pending"
    created_at: float = 0.0
    updated_at: float = 0.0
    logs: list[str] = field(default_factory=list)
    events: list[WorkflowEvent] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)   # workflow memory (run-local)
    result: str | None = None
    waiting_for: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RUNS: dict[str, WorkflowRun] = {}


def _now() -> float:
    return time.time()


def _emit(run: WorkflowRun, etype: str, message: str, data: dict | None = None) -> None:
    ev = WorkflowEvent(ts=_now(), type=etype, message=message, data=data or {})
    run.events.append(ev)
    run.updated_at = ev.ts
    print(f"[CREWAI] {run.run_id} {etype} {message}", flush=True)
    if EVENT_SINK is not None:
        try:
            EVENT_SINK(run.run_id, asdict(ev))
        except Exception:
            pass


def _log(run: WorkflowRun, message: str) -> None:
    run.logs.append(message)
    run.updated_at = _now()


def _artifact(run: WorkflowRun, name: str, content_type: str, body: str) -> None:
    run.artifacts.append({"name": name, "content_type": content_type, "created_at": _now(), "body": body})
    _emit(run, "artifact_created", f"Artifact: {name}", {"name": name})


# ── Agents (clean-room pass functions) ───────────────────────────────────────
def _agent(run: WorkflowRun, name: str, role: str, note: str) -> None:
    _emit(run, "agent_started", f"{name} started", {"role": role})
    _log(run, f"{name} ({role}): {note}")
    run.findings.append(f"{name}: {note}")
    _emit(run, "agent_completed", f"{name} completed", {"role": role})


_CREW = [
    ("ResearchAgent", "researcher", "collected available context for: {input}"),
    ("CodeAuditAgent", "auditor", "scanned for risks/defects relevant to: {input}"),
    ("TestDesignerAgent", "tester", "drafted a focused test strategy for: {input}"),
    ("VerifierAgent", "verifier", "checked findings are evidence-backed"),
]


def _report(run: WorkflowRun) -> str:
    lines = [f"# {run.workflow_type} report", "", f"Request: {run.input}", "", "## Findings"]
    lines += [f"- {f}" for f in run.findings] or ["- (none)"]
    lines += ["", "_Clean-room CrewAI-style workflow. Agent passes are placeholders pending LLM wiring._"]
    return "\n".join(lines)


def _finish(run: WorkflowRun) -> None:
    run.status = "running"
    for name, role, note in _CREW:
        _agent(run, name, role, note.format(input=run.input))
    _agent(run, "ReportWriterAgent", "writer", "wrote the final report")
    _artifact(run, f"{run.workflow_type}_report", "text/markdown", _report(run))
    run.result = f"{run.workflow_type} completed: {len(run.findings)} findings."
    run.status = "completed"
    _emit(run, "workflow_completed", run.result)


def _run_passes(run: WorkflowRun) -> None:
    run.status = "running"
    _emit(run, "workflow_started", f"Started {run.workflow_type}")
    _agent(run, "ManagerAgent", "manager", "planned the crew and task order")
    if any(p in run.input.lower() for p in ("ask me", "need user", "need more")):
        run.status = "waiting_for_input"
        run.waiting_for = "additional_user_context"
        _emit(run, "human_input_required", "Workflow needs more user input")
        return
    _finish(run)


# ── Public API ───────────────────────────────────────────────────────────────
def create_run(workflow_type: str, user_input: str, metadata: dict | None = None) -> WorkflowRun:
    wtype = (workflow_type or "").strip()
    if wtype not in WORKFLOW_TYPES:
        raise ValueError(f"Unsupported workflow_type: {wtype!r} (allowed: {sorted(WORKFLOW_TYPES)})")
    run = WorkflowRun(run_id=f"wf_{uuid.uuid4().hex[:12]}", workflow_type=wtype,
                      input=str(user_input or ""), created_at=_now(), updated_at=_now())
    _RUNS[run.run_id] = run
    _run_passes(run)
    return run


def get_run(run_id: str) -> WorkflowRun | None:
    return _RUNS.get(run_id)


def list_runs() -> list[WorkflowRun]:
    return list(_RUNS.values())


def latest_run() -> WorkflowRun | None:
    return max(_RUNS.values(), key=lambda r: r.created_at) if _RUNS else None


def cancel_run(run_id: str) -> WorkflowRun | None:
    run = _RUNS.get(run_id)
    if run and run.status not in _TERMINAL:
        run.status = "cancelled"
        _emit(run, "workflow_cancelled", "Cancelled by user")
    return run


def continue_run(run_id: str, user_input: str) -> WorkflowRun | None:
    run = _RUNS.get(run_id)
    if not run or run.status != "waiting_for_input":
        return run
    run.status = "running"
    run.waiting_for = None
    run.input = f"{run.input} | {user_input}".strip(" |")
    _emit(run, "human_input_received", "User input received", {"user_input": user_input})
    # user supplied the missing context -> run the crew directly (skip the input gate)
    run.findings.clear()
    _finish(run)
    return run


def clear() -> None:  # test helper
    _RUNS.clear()


if __name__ == "__main__":  # ponytail: runnable self-check, no framework
    clear()
    r = create_run("router_audit", "audit the intent router")
    assert r.status == "completed" and r.artifacts, r
    assert get_run(r.run_id) is r and latest_run() is r
    w = create_run("codebase_research", "research this repo, ask me which module")
    assert w.status == "waiting_for_input", w
    assert continue_run(w.run_id, "the router").status == "completed"
    assert cancel_run(create_run("test_generation", "x").run_id) is not None
    try:
        create_run("bogus", "x"); assert False
    except ValueError:
        pass
    print("OK", len(list_runs()), "runs")
