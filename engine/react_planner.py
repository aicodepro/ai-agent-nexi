from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class ReActStep:
    thought: str = ""
    action: str = "tool_call"
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
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


def _json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        value = match.group(0)
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sanitize_public_text(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(?im)^\s*(thought|action|observation)\s*:.*$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1200]


def _observation_from_result(result: dict[str, Any]) -> str:
    message = str(result.get("message") or result.get("error") or "")
    status = "success" if result.get("success") is True else "failed"
    if result.get("expects_user_reply"):
        status = "needs_input"
    if result.get("requires_confirmation"):
        status = "needs_confirmation"
    return _sanitize_public_text(f"{status}: {message or 'No result message.'}")


class ReActPlanner:
    """Small ReAct loop that executes only registered, safety-checked tools."""

    def __init__(self) -> None:
        self.max_steps = max(1, int(os.getenv("REACT_MAX_STEPS", "10") or 10))
        self.max_retries = max(0, int(os.getenv("REACT_MAX_RETRIES", "1") or 1))
        self.timeout_seconds = max(1.0, float(os.getenv("REACT_TIMEOUT_SECONDS", "30") or 30))
        self.model = (os.getenv("REACT_MODEL") or os.getenv("GROQ_INTENT_MODEL") or "llama-3.3-70b-versatile").strip()
        self.temperature = float(os.getenv("REACT_TEMPERATURE", "0") or 0)
        self._interrupted: set[str] = set()
        self._retry_counts: dict[str, int] = {}
        self._tool_call_counts: dict[str, int] = {}

    def plan(self, user_input: str, context: dict | None = None) -> ReActPlan:
        plan = ReActPlan(session_id=f"react_{uuid.uuid4().hex[:8]}", user_input=str(user_input or ""), context=dict(context or {}))
        plan.messages = [
            {"role": "system", "content": self._system_prompt(user_input)},
            {"role": "user", "content": json.dumps({"request": user_input, "context": context or {}}, default=str)},
        ]
        print(f"[REACT] started session={plan.session_id}", flush=True)
        self._tool_call_counts.clear()
        while plan.status == "in_progress" and len(plan.steps) < self.max_steps:
            if plan.session_id in self._interrupted:
                plan.status = "interrupted"
                break
            if time.time() - plan.started_at > self.timeout_seconds:
                plan.status = "error"
                plan.error = "timeout"
                break
            next_step = self._next_step(plan)
            plan.steps.append(next_step)
            if next_step.action == "respond":
                plan.final_response = _sanitize_public_text(next_step.observation or "")
                next_step.status = "success"
                plan.status = "done"
                break
            if next_step.action != "tool_call":
                plan.status = "error"
                plan.error = next_step.observation or "Planner returned an invalid action."
                break
            self.execute_step(plan, len(plan.steps) - 1)
            if next_step.status == "failed":
                retries = self._retry_counts.get(plan.session_id, 0)
                if retries < self.max_retries:
                    self._retry_counts[plan.session_id] = retries + 1
                    error_msg = _sanitize_public_text(next_step.observation or "That step failed.")
                    print(f"[REACT] retry attempt={retries + 1}/{self.max_retries} tool={next_step.tool_name}", flush=True)
                    plan.messages.append({"role": "user", "content": f"Observation from {next_step.tool_name}: {error_msg}. Try a different approach or tool."})
                    continue
                plan.final_response = _sanitize_public_text(next_step.observation or "I couldn't complete that step.")
                plan.error = next_step.observation or "tool_failed"
                plan.status = "error"
                break
            plan.messages.append({"role": "user", "content": f"Observation from {next_step.tool_name}: {next_step.observation}"})
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

    def execute_step(self, plan: ReActPlan, step_index: int) -> ReActStep:
        step = plan.steps[step_index]
        step.status = "running"
        tool_name = str(step.tool_name or "")
        tool_input = dict(step.tool_input or {})
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
            step.status = "success" if isinstance(result, dict) and result.get("success") is True else "failed"
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

    def _next_step(self, plan: ReActPlan) -> ReActStep:
        raw = self._call_llm(plan.messages, self._tools_schema())
        action = str(raw.get("action") or "").strip().lower()
        if raw.get("tool_name") or action == "tool_call":
            return ReActStep(
                thought=str(raw.get("thought") or "")[:400],
                action="tool_call",
                tool_name=str(raw.get("tool_name") or raw.get("name") or ""),
                tool_input=dict(raw.get("tool_input") or raw.get("arguments") or {}),
            )
        message = raw.get("message") or raw.get("final_response") or raw.get("content") or ""
        if message:
            return ReActStep(thought=str(raw.get("thought") or "")[:400], action="respond", observation=_sanitize_public_text(str(message)), status="success")
        return ReActStep(action="error", observation="Planner returned no action.", status="failed")

    def _call_llm(self, messages: list[dict], tools_schema: list[dict]) -> dict:
        api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not api_key:
            return {"action": "respond", "message": "I need the ReAct planner model configured before I can run multi-step tasks."}
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": int(os.getenv("REACT_MAX_TOKENS", "700") or 700),
            "messages": messages,
            "tools": tools_schema,
            "tool_choice": "auto",
        }
        max_retries = max(0, int(os.getenv("REACT_MAX_RETRIES", "2")))
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=float(os.getenv("REACT_LLM_TIMEOUT_SECONDS", "10") or 10),
                )
                if response.status_code == 429 and attempt < max_retries:
                    backoff = 2 ** attempt
                    print(f"[REACT] rate_limited retry_in={backoff}s attempt={attempt + 1}/{max_retries}", flush=True)
                    time.sleep(backoff)
                    continue
                if response.status_code >= 400:
                    return {"action": "respond", "message": "I could not reach the ReAct planner model."}
                message = response.json()["choices"][0]["message"]
                break
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    print(f"[REACT] transient_error={type(exc).__name__} retry_in={backoff}s attempt={attempt + 1}/{max_retries}", flush=True)
                    time.sleep(backoff)
                    continue
                return {"action": "respond", "message": "I could not reach the ReAct planner model."}
            except Exception:
                return {"action": "respond", "message": "I could not reach the ReAct planner model."}
        else:
            return {"action": "respond", "message": "I could not reach the ReAct planner model."}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            call = tool_calls[0]
            function = call.get("function") or {}
            return {
                "action": "tool_call",
                "tool_name": function.get("name", ""),
                "tool_input": _json_object(function.get("arguments", "{}")),
            }
        content = str(message.get("content") or "")
        parsed = _json_object(content)
        if parsed:
            return parsed
        return {"action": "respond", "message": content}

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
            "Never claim an action succeeded unless the tool observation says it was verified."
            + (f"\n{reflection}" if reflection else "")
        )

    def _emit_status(self, status: str, text: str = "") -> None:
        try:
            from engine.ui_state_manager import emit_state
            emit_state("thinking", source="react", status=status, text=text, force=True)
        except Exception:
            pass
