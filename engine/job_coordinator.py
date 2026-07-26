"""What NEXI is trying to achieve, and how far it has got.

Two things live here because neither is meaningful alone: a Goal is what the
user wants, a Job is a unit of work serving it.

The defect this addresses is truthfulness about progress. Starting a workflow
was reported as a verified success - the live trace emitted `verified=true`
before the planner agent had run. `_accepted()` stopped that lie at the tool
boundary; this gives the runtime somewhere to record what is ACTUALLY happening
so NEXI can say

    "I created the project structure and installed the dependencies. The build
     failed in the authentication module, so I'm diagnosing that now."

instead of "Task completed."

Terminal success is a separate, explicit step: `mark_verified()`. A job that
merely stopped running is not a job that worked.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


#: States from which no further work happens.
TERMINAL_STATES = frozenset({
    JobState.COMPLETED, JobState.PARTIAL_FAILURE,
    JobState.FAILED, JobState.CANCELLED,
})

#: States where NEXI is blocked on somebody or something else.
WAITING_STATES = frozenset({
    JobState.WAITING_FOR_INPUT, JobState.WAITING_FOR_APPROVAL,
    JobState.WAITING_FOR_TOOL, JobState.PAUSED,
})


@dataclass
class Job:
    job_id: str
    goal_id: str
    title: str
    state: JobState = JobState.QUEUED
    depends_on: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    error: str = ""
    blocked_reason: str = ""
    attempts: int = 0
    max_attempts: int = 3
    verified: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def is_waiting(self) -> bool:
        return self.state in WAITING_STATES

    def can_retry(self) -> bool:
        return self.state is JobState.FAILED and self.attempts < self.max_attempts

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "title": self.title, "state": self.state.value,
                "verified": self.verified, "attempts": self.attempts,
                "error": self.error, "blocked_reason": self.blocked_reason,
                "evidence": list(self.evidence), "depends_on": list(self.depends_on)}


@dataclass
class Goal:
    goal_id: str
    description: str
    session_id: str = ""
    success_conditions: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    future_approval: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"goal_id": self.goal_id, "description": self.description,
                "session_id": self.session_id,
                "success_conditions": list(self.success_conditions),
                "missing_information": list(self.missing_information),
                "future_approval": self.future_approval}


class JobCoordinator:
    """One owner for goals and the jobs serving them."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._goals: dict[str, Goal] = {}
        self._jobs: dict[str, Job] = {}
        self._active_goal_id: str = ""

    # --- goals ---------------------------------------------------------

    def start_goal(self, description: str, *, session_id: str = "",
                   success_conditions: list[str] | None = None) -> Goal:
        goal = Goal(goal_id=uuid.uuid4().hex[:10],
                    description=(description or "").strip()[:300],
                    session_id=session_id or "",
                    success_conditions=list(success_conditions or []),
                    created_at=time.time())
        with self._lock:
            self._goals[goal.goal_id] = goal
            self._active_goal_id = goal.goal_id
        print(f"[GOAL] started id={goal.goal_id} goal={goal.description[:60]}", flush=True)
        return goal

    def active_goal(self) -> Goal | None:
        with self._lock:
            return self._goals.get(self._active_goal_id)

    def set_missing_information(self, fields: list[str]) -> None:
        with self._lock:
            goal = self._goals.get(self._active_goal_id)
            if goal is not None:
                goal.missing_information = list(fields or [])

    # --- jobs ----------------------------------------------------------

    def add_job(self, title: str, *, goal_id: str = "",
                depends_on: list[str] | None = None, max_attempts: int = 3) -> Job:
        with self._lock:
            gid = goal_id or self._active_goal_id
            job = Job(job_id=uuid.uuid4().hex[:10], goal_id=gid,
                      title=(title or "").strip()[:200],
                      depends_on=list(depends_on or []),
                      max_attempts=max(1, int(max_attempts)),
                      created_at=time.time(), updated_at=time.time())
            self._jobs[job.job_id] = job
        print(f"[JOB] queued id={job.job_id} title={job.title[:60]}", flush=True)
        return job

    def set_state(self, job_id: str, state: JobState, *, error: str = "",
                  blocked_reason: str = "", evidence: str = "") -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if state is JobState.RUNNING and job.state is not JobState.RUNNING:
                job.attempts += 1
            job.state = state
            job.updated_at = time.time()
            if error:
                job.error = error[:300]
            if blocked_reason:
                job.blocked_reason = blocked_reason[:200]
            if evidence:
                job.evidence.append(evidence[:300])
            # Leaving a terminal-success state without verification must not
            # leave a stale verified flag behind.
            if state is not JobState.COMPLETED:
                job.verified = False
        print(f"[JOB] state id={job_id} state={state.value}"
              f"{(' reason=' + blocked_reason) if blocked_reason else ''}", flush=True)
        return job

    def mark_verified(self, job_id: str, evidence: str) -> Job | None:
        """The only way a job becomes a verified success.

        Deliberately separate from COMPLETED: reaching the end of execution is
        not proof the postcondition holds. An independent verifier supplies the
        evidence; the executor cannot mark its own work verified.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.state is not JobState.COMPLETED:
                print(f"[JOB] verify_rejected id={job_id} state={job.state.value}", flush=True)
                return job
            job.verified = True
            job.evidence.append(str(evidence or "")[:300])
            job.updated_at = time.time()
        print(f"[JOB] verified id={job_id}", flush=True)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def jobs_for(self, goal_id: str = "") -> list[Job]:
        with self._lock:
            gid = goal_id or self._active_goal_id
            return [j for j in self._jobs.values() if j.goal_id == gid]

    def blocking_dependencies(self, job_id: str) -> list[str]:
        """Dependency job ids that are not verified-complete yet."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return []
            return [d for d in job.depends_on
                    if not (self._jobs.get(d) and self._jobs[d].verified)]

    def cancel_goal(self, reason: str = "cancelled") -> int:
        with self._lock:
            gid = self._active_goal_id
            affected = [j for j in self._jobs.values()
                        if j.goal_id == gid and not j.is_terminal()]
            for job in affected:
                job.state = JobState.CANCELLED
                job.blocked_reason = reason
                job.updated_at = time.time()
            self._active_goal_id = ""
        print(f"[GOAL] cancelled jobs={len(affected)} reason={reason}", flush=True)
        return len(affected)

    # --- what the user can ask -----------------------------------------

    def progress_summary(self) -> dict[str, Any]:
        """Answers "what are you doing / what's left / why are you stuck"."""
        with self._lock:
            goal = self._goals.get(self._active_goal_id)
            jobs = [j for j in self._jobs.values() if j.goal_id == self._active_goal_id]
        done = [j.title for j in jobs if j.verified]
        # COMPLETED but unverified is NOT done. Reporting it as finished is the
        # exact lie this module exists to prevent.
        unverified = [j.title for j in jobs if j.state is JobState.COMPLETED and not j.verified]
        active = [j.title for j in jobs if j.state is JobState.RUNNING]
        waiting = [{"title": j.title, "reason": j.blocked_reason or j.state.value}
                   for j in jobs if j.is_waiting()]
        failed = [{"title": j.title, "error": j.error}
                  for j in jobs if j.state in (JobState.FAILED, JobState.PARTIAL_FAILURE)]
        return {
            "goal": goal.description if goal else "",
            "completed": done,
            "completed_unverified": unverified,
            "in_progress": active,
            "waiting": waiting,
            "failed": failed,
            "missing_information": list(goal.missing_information) if goal else [],
            "all_done": bool(jobs) and all(j.verified for j in jobs),
        }

    def reset_for_tests(self) -> None:
        with self._lock:
            self._goals.clear()
            self._jobs.clear()
            self._active_goal_id = ""


_coordinator = JobCoordinator()


def get_coordinator() -> JobCoordinator:
    return _coordinator
