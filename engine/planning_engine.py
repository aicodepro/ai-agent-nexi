from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    step_id: str
    description: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: float = 0.0
    completed_at: float = 0.0
    expected_output: str = ""

    @property
    def duration_s(self) -> float:
        if self.completed_at > 0:
            return self.completed_at - self.started_at
        return time.time() - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "action": self.action,
            "params": self.params,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "error": self.error,
            "duration_s": round(self.duration_s, 2) if self.started_at else 0,
        }


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = 0.0
    completed_at: float = 0.0
    status: str = "created"
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED))
        return done / len(self.steps)

    @property
    def is_done(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps)

    @property
    def current_step(self) -> Optional[PlanStep]:
        for s in self.steps:
            if s.status == StepStatus.IN_PROGRESS:
                return s
        for s in self.steps:
            if s.status == StepStatus.PENDING:
                return s
        return None

    def summary(self) -> str:
        lines = [f"Plan: {self.goal}", f"Progress: {int(self.progress * 100)}% ({self.status})"]
        for s in self.steps:
            mark = {"pending": "○", "in_progress": "→", "completed": "✓", "failed": "✗", "skipped": "–"}
            lines.append(f"  {mark.get(s.status.value, '?')} {s.step_id}: {s.description}")
        return "\n".join(lines)


class PlanningEngine:
    def __init__(self, tool_registry=None):
        self._tool_registry = tool_registry
        self.active_plan: Optional[Plan] = None
        self._history: list[Plan] = []

    def set_tool_registry(self, registry):
        self._tool_registry = registry

    def decompose(self, goal: str, context: Optional[dict[str, Any]] = None) -> Plan:
        plan = Plan(goal=goal, created_at=time.time(), context=context or {})
        available_tools = []
        if self._tool_registry:
            available_tools = [t.name for t in self._tool_registry.list_tools()]

        prompt = (
            f"Decompose this goal into sequential steps:\n{goal}\n\n"
            f"Available tools: {', '.join(available_tools) if available_tools else 'none (reasoning only)'}\n\n"
            "Return a JSON array of steps, each with: step_id, description, action (tool name or 'reason'), "
            "params (dict), depends_on (list of step_ids), expected_output (what success looks like). "
            "Max 8 steps."
        )
        from engine.brain.llm_interface import llm_complete
        try:
            raw = llm_complete(system="You are a planning agent. Output ONLY valid JSON.", prompt=prompt, max_tokens=2000)
            steps_data = self._parse_steps(raw)
            for sd in steps_data:
                plan.steps.append(PlanStep(
                    step_id=sd.get("step_id", f"s{len(plan.steps)+1}"),
                    description=sd.get("description", ""),
                    action=sd.get("action", "reason"),
                    params=sd.get("params", {}),
                    depends_on=sd.get("depends_on", []),
                    expected_output=sd.get("expected_output", ""),
                ))
        except Exception as e:
            logger.warning(f"LLM decompose failed, using fallback: {e}")
            plan.steps.append(PlanStep(
                step_id="s1",
                description=f"Process goal: {goal[:200]}",
                action="reason",
                params={"goal": goal},
            ))

        self.active_plan = plan
        self._history.append(plan)
        return plan

    def _parse_steps(self, raw: str) -> list[dict[str, Any]]:
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "steps" in parsed:
            return parsed["steps"]
        if isinstance(parsed, list):
            return parsed
        return []

    def next_step(self) -> Optional[PlanStep]:
        if not self.active_plan:
            return None
        for step in self.active_plan.steps:
            if step.status != StepStatus.PENDING:
                continue
            deps = [s for s in self.active_plan.steps if s.step_id in step.depends_on]
            if all(d.status == StepStatus.COMPLETED for d in deps):
                return step
        return None

    def mark_step(self, step_id: str, status: StepStatus, result: Any = None, error: Optional[str] = None):
        for step in (self.active_plan.steps if self.active_plan else []):
            if step.step_id == step_id:
                step.status = status
                if status == StepStatus.IN_PROGRESS:
                    step.started_at = time.time()
                if status in (StepStatus.COMPLETED, StepStatus.FAILED):
                    step.completed_at = time.time()
                if result is not None:
                    step.result = result
                if error:
                    step.error = error
                break
        if self.active_plan:
            if self.active_plan.is_done:
                self.active_plan.completed_at = time.time()
                self.active_plan.status = "completed"

    def reflect(self) -> Optional[str]:
        if not self.active_plan or not self.active_plan.is_done:
            return None
        outcome = []
        plan = self.active_plan
        outcome.append(f"Goal: {plan.goal}")
        outcome.append(f"Status: {plan.status} in {round(plan.completed_at - plan.created_at, 1)}s")
        for step in plan.steps:
            icon = "✓" if step.status == StepStatus.COMPLETED else "✗" if step.status == StepStatus.FAILED else "–"
            outcome.append(f"  {icon} {step.step_id}: {step.description} ({step.status.value})")
            if step.error:
                outcome.append(f"    Error: {step.error}")
        return "\n".join(outcome)

    def get_plan(self) -> Optional[Plan]:
        return self.active_plan

    def recent_plans(self, n: int = 3) -> list[Plan]:
        return self._history[-n:]

    def can_proceed(self, step: PlanStep) -> bool:
        deps = [s for s in (self.active_plan.steps if self.active_plan else []) if s.step_id in step.depends_on]
        return all(d.status == StepStatus.COMPLETED for d in deps)
