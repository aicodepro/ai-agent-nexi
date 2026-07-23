from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from engine.memory_safety import redact_sensitive


_RESERVED_MODEL_ARGUMENT_KEYS = frozenset({
    "approved",
    "approval",
    "approval_id",
    "approval_token",
    "auth",
    "auth_token",
    "authorization",
    "authorization_id",
    "authorization_token",
    "authorized",
    "confirmed",
    "confirmation",
    "confirmation_id",
    "confirmation_token",
    "_studio_auth",
})
_RESERVED_MODEL_ARGUMENT_TOKENS = frozenset({
    "approval",
    "approve",
    "approved",
    "auth",
    "authorization",
    "authorized",
    "authorisation",
    "authorised",
    "confirmation",
    "confirm",
    "confirmed",
    "consent",
    "permission",
})

@dataclass
class ReActStep:
    thought: str = ""
    action: str = "tool_call"
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_call_id: str = ""
    observation: str | None = None
    status: str = "pending"


@dataclass
class ReActPlan:
    session_id: str = ""
    user_input: str = ""
    steps: list[ReActStep] = field(default_factory=list)
    final_response: str = ""
    status: str = "in_progress"
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    allowed_tool_names: frozenset[str] = field(default_factory=frozenset)
    unresolved_tool_error: str | None = None
    failed_tool_obligations: list[dict[str, str]] = field(default_factory=list)
    verified_tool_results: int = 0


def _sanitize_public_text(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(?im)^\s*(thought|action|observation)\s*:.*$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1200]


def _redact_provider_observation(text: str) -> str:
    value = redact_sensitive(str(text or ""))
    value = re.sub(r"(?i)\b(api[_ -]?key|token|password|secret|cookie|authorization)\b\s*(?:is|:|=)\s*\S+", r"\1=[REDACTED]", value)
    value = re.sub(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED_JWT]", value)
    value = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", value, flags=re.I)
    return value


def _observation_from_result(result: dict[str, Any]) -> str:
    message = str(result.get("message") or result.get("error") or "")
    status = "success" if result.get("success") is True else "failed"
    if result.get("expects_user_reply"):
        status = "needs_input"
    if result.get("requires_confirmation"):
        status = "needs_confirmation"
    return _sanitize_public_text(_redact_provider_observation(f"{status}: {message or 'No result message.'}"))


def _strip_reserved_arguments(value: Any) -> Any:
    """Remove model-supplied authorization/approval claims at every nesting level."""
    if isinstance(value, dict):
        return {
            key: _strip_reserved_arguments(item)
            for key, item in value.items()
            if not _is_reserved_argument_key(key)
        }
    if isinstance(value, list):
        return [_strip_reserved_arguments(item) for item in value]
    return value


def _is_reserved_argument_key(key: Any) -> bool:
    raw = str(key).strip().lower()
    if raw in _RESERVED_MODEL_ARGUMENT_KEYS:
        return True
    tokens = {token for token in re.split(r"[^a-z0-9]+", raw) if token}
    return bool(tokens & _RESERVED_MODEL_ARGUMENT_TOKENS)


def _schema_tool_names(tools_schema: list[dict[str, Any]]) -> frozenset[str]:
    names: set[str] = set()
    for item in tools_schema:
        function = item.get("function") if isinstance(item, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return frozenset(names)


class ReActPlanner:
    """Small ReAct loop that executes only registered, safety-checked tools."""

    def __init__(self) -> None:
        self.max_steps = max(1, int(os.getenv("REACT_MAX_STEPS", "10") or 10))
        self.max_retries = max(0, int(os.getenv("REACT_MAX_RETRIES", "1") or 1))
        self.timeout_seconds = max(1.0, float(os.getenv("REACT_TIMEOUT_SECONDS", "30") or 30))
        # Pick a model that can actually survive a multi-turn tool loop (REACT_MODEL
        # still wins). Guards the harmony-token leak: gpt-oss corrupts tool names on
        # the 2nd turn, which Groq rejects with a hard 400.
        from engine.model_registry import select_model
        self.model = select_model("react_tools")
        self.temperature = float(os.getenv("REACT_TEMPERATURE", "0") or 0)
        self._interrupted: set[str] = set()
        self._retry_counts: dict[str, int] = {}
        self._tool_call_counts: dict[str, int] = {}

    def plan(self, user_input: str, context: dict | None = None) -> ReActPlan:
        tools_schema = self._tools_schema()
        plan = ReActPlan(
            session_id=f"react_{uuid.uuid4().hex[:8]}",
            user_input=str(user_input or ""),
            context=dict(context or {}),
            allowed_tool_names=_schema_tool_names(tools_schema),
        )
        # Situational state, so "handle it" / "again" resolve to something. Callers pass
        # the router decision as context, which carries no world data -- read it here so
        # every entry point into the loop gets it, not just command.py's react branch.
        world: dict[str, Any] = {}
        try:
            from engine.world_model import get_world

            snapshot = get_world()
            world = {key: snapshot[key] for key in ("last_action", "last_result", "environment") if snapshot.get(key)}
        except Exception:
            world = {}
        plan.messages = [
            {"role": "system", "content": self._system_prompt(user_input)},
            {"role": "user", "content": json.dumps({"request": user_input, "context": context or {}, "world": world}, default=str)},
        ]
        print(f"[REACT] started session={plan.session_id}", flush=True)
        self._tool_call_counts.clear()
        deterministic_steps = self._deterministic_steps(plan)
        if deterministic_steps:
            return self._execute_deterministic_steps(plan, deterministic_steps)
        while plan.status == "in_progress" and len(plan.steps) < self.max_steps:
            if plan.session_id in self._interrupted:
                plan.status = "interrupted"
                break
            remaining_timeout = self.timeout_seconds - (time.time() - plan.started_at)
            if remaining_timeout <= 0:
                plan.status = "error"
                plan.error = "timeout"
                break
            next_step = self._next_step(plan, remaining_timeout, tools_schema)
            plan.steps.append(next_step)
            if next_step.action == "respond":
                if plan.failed_tool_obligations:
                    next_step.status = "failed"
                    plan.final_response = "The requested action remains unverified because a required tool attempt failed or was blocked."
                    plan.error = plan.failed_tool_obligations[0].get("error") or "tool_failed"
                    plan.unresolved_tool_error = plan.error
                    plan.status = "error"
                    break
                if plan.verified_tool_results < 1:
                    next_step.status = "failed"
                    plan.final_response = "The requested multi-step action remains unverified because no tool result was verified."
                    plan.error = "verified_tool_result_required"
                    plan.status = "error"
                    break
                plan.final_response = _sanitize_public_text(next_step.observation or "")
                next_step.status = "success"
                plan.status = "done"
                break
            if next_step.action != "tool_call":
                plan.status = "error"
                plan.error = next_step.observation or "Planner returned an invalid action."
                break
            self.execute_step(plan, len(plan.steps) - 1)
            self._append_tool_result(plan, next_step)
            if next_step.status == "failed":
                failure_error = next_step.observation or "tool_failed"
                plan.failed_tool_obligations.append({
                    "tool_name": str(next_step.tool_name or ""),
                    "tool_call_id": str(next_step.tool_call_id or ""),
                    "error": failure_error,
                })
                plan.unresolved_tool_error = failure_error
                retries = self._retry_counts.get(plan.session_id, 0)
                if retries < self.max_retries:
                    self._retry_counts[plan.session_id] = retries + 1
                    error_msg = _sanitize_public_text(next_step.observation or "That step failed.")
                    print(f"[REACT] retry attempt={retries + 1}/{self.max_retries} tool={next_step.tool_name}", flush=True)
                    plan.messages.append({"role": "user", "content": f"That tool failed: {error_msg}. Try a different approach or tool."})
                    continue
                plan.final_response = _sanitize_public_text(next_step.observation or "I couldn't complete that step.")
                plan.error = next_step.observation or "tool_failed"
                plan.status = "error"
                break
            plan.verified_tool_results += 1
            # A verified retry discharges only failures for that same tool. An
            # unrelated successful tool cannot erase a prior failed obligation.
            plan.failed_tool_obligations = [
                obligation
                for obligation in plan.failed_tool_obligations
                if obligation.get("tool_name") != str(next_step.tool_name or "")
            ]
            plan.unresolved_tool_error = (
                plan.failed_tool_obligations[0].get("error")
                if plan.failed_tool_obligations
                else None
            )
            pattern = f"{next_step.tool_name}:{json.dumps(next_step.tool_input or {}, default=str, sort_keys=True)}"
            count = self._tool_call_counts.get(pattern, 0) + 1
            self._tool_call_counts[pattern] = count
            if count > 2:
                done_tools = [s.tool_name for s in plan.steps if s.status == "success" and s.tool_name]
                report = f"I completed steps: {', '.join(done_tools)} before stopping to avoid a loop." if done_tools else "I stopped because I was repeating the same step."
                plan.final_response = report
                plan.error = "repetition"
                plan.status = "error"
                print(f"[REACT] repetition_detected tool={next_step.tool_name} count={count}", flush=True)
                break
        if plan.status == "in_progress":
            plan.status = "error"
            plan.error = "max_steps"
        return plan

    def _deterministic_steps(self, plan: ReActPlan) -> list[ReActStep]:
        """Build an offline plan only when every atomic command maps to a safe schema tool."""
        try:
            from engine.groq_intent_router_v2 import _deterministic_router, _finalize
            from engine.router.compound import split_steps

            commands = split_steps(plan.user_input)
            if len(commands) < 2 or len(commands) > self.max_steps:
                return []
            steps: list[ReActStep] = []
            route_context = dict(plan.context)
            route_context["source"] = "react"
            for command in commands:
                decision = _finalize(_deterministic_router(command, route_context), command)
                if decision.get("route") not in {"tool", "output", "workflow"}:
                    return []
                if decision.get("missing_slots") or decision.get("expects_user_reply"):
                    return []
                tool_name = str(decision.get("intent") or "")
                if tool_name not in plan.allowed_tool_names:
                    return []
                slots = decision.get("slots") or {}
                if not isinstance(slots, dict):
                    return []
                steps.append(ReActStep(
                    action="tool_call",
                    tool_name=tool_name,
                    tool_input=dict(slots),
                    tool_call_id=f"call_{uuid.uuid4().hex[:12]}",
                ))
            return steps
        except Exception:
            return []

    def _execute_deterministic_steps(self, plan: ReActPlan, steps: list[ReActStep]) -> ReActPlan:
        for step in steps:
            if plan.session_id in self._interrupted:
                plan.status = "interrupted"
                return plan
            if time.time() - plan.started_at >= self.timeout_seconds:
                plan.status = "error"
                plan.error = "timeout"
                return plan
            plan.steps.append(step)
            self.execute_step(plan, len(plan.steps) - 1)
            self._append_tool_result(plan, step)
            if step.status != "success":
                error = step.observation or "tool_failed"
                plan.failed_tool_obligations.append({
                    "tool_name": str(step.tool_name or ""),
                    "tool_call_id": str(step.tool_call_id or ""),
                    "error": error,
                })
                plan.unresolved_tool_error = error
                plan.final_response = _sanitize_public_text(error)
                plan.error = error
                plan.status = "error"
                return plan
            plan.verified_tool_results += 1
        plan.final_response = _sanitize_public_text(" ".join(
            step.observation or "" for step in plan.steps if step.status == "success"
        ))
        plan.status = "done"
        return plan

    @staticmethod
    def _append_tool_result(plan: ReActPlan, step: ReActStep) -> None:
        plan.messages.append({
            "role": "tool",
            "tool_call_id": step.tool_call_id,
            "name": str(step.tool_name or ""),
            "content": _redact_provider_observation(str(step.observation or "No result message.")),
        })

    def execute_step(self, plan: ReActPlan, step_index: int) -> ReActStep:
        step = plan.steps[step_index]
        step.status = "running"
        tool_name = str(step.tool_name or "")
        if not isinstance(step.tool_input, dict):
            step.status = "failed"
            step.observation = "Planner returned invalid tool arguments."
            return step
        if tool_name not in plan.allowed_tool_names:
            step.status = "failed"
            step.observation = "Planner requested a tool that was not in this plan's immutable schema."
            return step
        tool_input = dict(_strip_reserved_arguments(step.tool_input))
        step.tool_input = tool_input
        self._emit_status("running_tool", tool_name)
        try:
            from engine.safety_gate import execution_is_safe
            safety = execution_is_safe(tool_name, tool_input, user_text=plan.user_input, context=plan.context)
            if not safety.get("allowed"):
                step.status = "failed"
                step.observation = _sanitize_public_text(str(safety.get("reason") or "Safety gate blocked this action."))
                print(f"[REACT] tool_blocked name={tool_name} reason={safety.get('category')}", flush=True)
                return step
            from engine.tool_registry import execute_tool
            result = execute_tool(tool_name, tool_input)
            step.observation = _observation_from_result(result if isinstance(result, dict) else {})
            step.status = "success" if isinstance(result, dict) and result.get("success") is True and result.get("verified") is True else "failed"
            print(f"[REACT] tool_done name={tool_name} status={step.status}", flush=True)
            return step
        except Exception as exc:
            step.status = "failed"
            step.observation = f"Tool failed safely: {type(exc).__name__}"
            print(f"[REACT] tool_failed name={tool_name} reason={type(exc).__name__}", flush=True)
            return step

    def continue_planning(self, plan: ReActPlan) -> ReActPlan:
        return self.plan(plan.user_input, plan.context)

    def finalize(self, plan: ReActPlan) -> str:
        if plan.status == "done" and plan.final_response:
            return _sanitize_public_text(plan.final_response)
        if plan.status == "interrupted":
            return "Stopped."
        if plan.final_response:
            return _sanitize_public_text(plan.final_response)
        if plan.error == "timeout":
            return "I could not finish that multi-step task before the timeout."
        if plan.error == "max_steps":
            return "I stopped because the task took too many steps."
        error_str = str(plan.error or "")
        if "safety" in error_str.lower() or "blocked" in error_str.lower():
            return f"I could not complete that: {error_str}"
        if "unavailable" in error_str.lower() or "not wired" in error_str.lower() or "not available" in error_str.lower():
            return f"That tool is not available: {error_str}"
        if error_str and error_str != "tool_failed":
            return f"I could not complete that: {error_str}"
        return "I could not complete that multi-step task."

    def interrupt(self, plan: ReActPlan) -> None:
        self._interrupted.add(plan.session_id)
        plan.status = "interrupted"

    def _next_step(self, plan: ReActPlan, timeout: float, tools_schema: list[dict[str, Any]]) -> ReActStep:
        raw = self._call_llm(plan.messages, tools_schema, timeout=timeout)
        if not isinstance(raw, dict):
            return ReActStep(action="error", observation="Planner returned an invalid response.", status="failed")
        action = str(raw.get("action") or "").strip().lower()
        if action == "error":
            return ReActStep(action="error", observation=_sanitize_public_text(str(raw.get("error") or "Planner provider failed.")), status="failed")
        if raw.get("tool_name") or action == "tool_call":
            tool_name = raw.get("tool_name") or raw.get("name")
            tool_input = raw.get("tool_input") if "tool_input" in raw else raw.get("arguments", {})
            if not isinstance(tool_name, str) or not tool_name.strip():
                return ReActStep(action="error", observation="Planner returned an invalid tool name.", status="failed")
            tool_name = tool_name.strip()
            if tool_name not in plan.allowed_tool_names:
                return ReActStep(action="error", observation="Planner requested a tool outside this plan's immutable schema.", status="failed")
            if not isinstance(tool_input, dict):
                return ReActStep(action="error", observation="Planner returned invalid tool arguments.", status="failed")
            tool_input = _strip_reserved_arguments(tool_input)
            tool_call_id = raw.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                tool_call_id = f"call_{uuid.uuid4().hex[:12]}"
            # Rebuild the protocol message from sanitized arguments. Never echo
            # provider-supplied authorization fields or extra tool calls.
            assistant_message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(tool_input, default=str)},
                }],
            }
            plan.messages.append(dict(assistant_message))
            return ReActStep(
                thought=str(raw.get("thought") or "")[:400],
                action="tool_call",
                tool_name=tool_name,
                tool_input=dict(tool_input),
                tool_call_id=tool_call_id,
            )
        message = raw.get("message") or raw.get("final_response") or raw.get("content") or ""
        if message:
            return ReActStep(thought=str(raw.get("thought") or "")[:400], action="respond", observation=_sanitize_public_text(str(message)), status="success")
        return ReActStep(action="error", observation="Planner returned no action.", status="failed")

    def _call_llm(self, messages: list[dict], tools_schema: list[dict], *, timeout: float) -> dict:
        if timeout <= 0:
            return {"action": "error", "error": "timeout"}
        try:
            from engine.providers import get_intent_provider
            provider = get_intent_provider()
        except Exception as exc:
            return {"action": "error", "error": f"provider_init_failed:{type(exc).__name__}"}
        if provider is None:
            return {"action": "error", "error": "provider_unavailable"}
        try:
            if not provider.is_available():
                return {"action": "error", "error": "provider_unavailable"}
            result = provider.route_with_tools(
                messages,
                tools_schema,
                model=self.model,
                timeout=timeout,
                tool_choice="auto",
            )
        except Exception as exc:
            return {"action": "error", "error": f"provider_failed:{type(exc).__name__}"}
        if not result.ok:
            return {"action": "error", "error": f"provider_failed:{result.error_code or 'unknown'}"}
        if result.tool_call is not None:
            call = result.tool_call
            if not isinstance(call, dict):
                return {"action": "error", "error": "invalid_tool_call"}
            name = call.get("name")
            arguments = call.get("arguments")
            if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                return {"action": "error", "error": "invalid_tool_arguments"}
            return {
                "action": "tool_call",
                "tool_name": name,
                "tool_input": arguments,
                "tool_call_id": str(call.get("id") or ""),
                "_assistant_message": result.assistant_message,
            }
        if result.decision is not None:
            if not isinstance(result.decision, dict):
                return {"action": "error", "error": "invalid_provider_decision"}
            return dict(result.decision)
        if result.raw_text:
            return {"action": "respond", "message": result.raw_text}
        return {"action": "error", "error": "empty_provider_response"}

    def _tools_schema(self) -> list[dict]:
        try:
            from engine.tool_registry import tools_openai_schema
            return tools_openai_schema()
        except Exception:
            return []

    def _system_prompt(self, user_input: str) -> str:
        reflection = ""
        try:
            from engine.reflection_memory import ReflectionMemory
            reflection = ReflectionMemory.get_context(user_input, max_lessons=3)
        except Exception:
            reflection = ""
        return (
            "You are Nexi ReAct planner. Use registered tools for multi-step tasks. "
            "Do not reveal chain-of-thought. Return final user-facing messages only, or call one tool. "
            "Never claim an action succeeded unless the tool observation says it was verified. "
            "For executable multi-step requests, do not finish before at least one verified tool result."
            + (f"\n{reflection}" if reflection else "")
        )

    def _emit_status(self, status: str, text: str = "") -> None:
        try:
            from engine.ui_state_manager import emit_state
            emit_state("thinking", source="react", status=status, text=text, force=True)
        except Exception:
            pass
