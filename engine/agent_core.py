from __future__ import annotations

import json
import time
import logging
import traceback
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

from engine.agent_state import AgentContext, AgentPhase, SessionState, TurnState
from engine.agent_context import ContextManager
from engine.tool_schema import ToolRegistry, ToolSchema, ToolResult
from engine.planning_engine import PlanningEngine, Plan, PlanStep, StepStatus

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    max_tool_calls_per_turn: int = 20
    max_reasoning_tokens: int = 2000
    max_plan_steps: int = 8
    session_timeout_s: float = 300.0
    idle_timeout_s: float = 60.0
    max_consecutive_errors: int = 3
    enable_planning: bool = True
    enable_tools: bool = True
    enable_auto_followup: bool = False
    debug: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tool_calls_per_turn": self.max_tool_calls_per_turn,
            "max_reasoning_tokens": self.max_reasoning_tokens,
            "max_plan_steps": self.max_plan_steps,
            "session_timeout_s": self.session_timeout_s,
            "idle_timeout_s": self.idle_timeout_s,
            "enable_planning": self.enable_planning,
            "enable_tools": self.enable_tools,
        }


class AgentCore:
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        tool_registry: Optional[ToolRegistry] = None,
        llm_call: Optional[Callable] = None,
    ):
        self.config = config or AgentConfig()
        self.tools = tool_registry or ToolRegistry()
        self.context = AgentContext()
        self.context_manager = ContextManager()
        self.planner = PlanningEngine(self.tools)
        self._llm_call = llm_call
        self._callbacks: dict[str, list[Callable]] = {}
        self._running = False

    def set_llm_call(self, func: Callable):
        self._llm_call = func

    def on(self, event: str, callback: Callable):
        self._callbacks.setdefault(event, []).append(callback)

    def _emit(self, event: str, **data):
        for cb in self._callbacks.get(event, []):
            try:
                cb(**data)
            except Exception as e:
                logger.warning(f"Callback {event} failed: {e}")

    def _llm(self, system: str, prompt: str, max_tokens: int = 1000) -> str:
        if self._llm_call:
            return self._llm_call(system=system, prompt=prompt, max_tokens=max_tokens)
        from engine.brain.llm_interface import llm_complete
        return llm_complete(system=system, prompt=prompt, max_tokens=max_tokens)

    # ── Agent Loop ────────────────────────────────────────────

    def process_input(self, user_input: str) -> tuple[str, Optional[Plan]]:
        if not self._running:
            self.start_session()

        session = self.context.session
        turn = session.new_turn(user_input)
        self._emit("turn_start", turn=turn)

        try:
            result = self._think_act_observe(user_input, turn)
            self._finish_turn(turn, result)
            return result, self.planner.get_plan()
        except Exception as e:
            logger.error(f"Agent loop failed: {e}\n{traceback.format_exc()}")
            session.record_error(str(e))
            self._emit("error", error=str(e))
            error_msg = f"Error: {e}"
            self._finish_turn(turn, error_msg)
            return error_msg, None

    def _think_act_observe(self, user_input: str, turn: TurnState) -> str:
        plan = self._maybe_plan(user_input, turn)

        tool_calls = 0
        max_iter = self.config.max_tool_calls_per_turn + 5

        for iteration in range(max_iter):
            turn.phase = AgentPhase.THINKING
            self._emit("think", turn=turn)

            next_step = self.planner.next_step() if plan else None

            context = self._build_prompt_context(user_input, turn, next_step)

            response = self._llm(
                system=self._build_system_prompt(),
                prompt=context,
                max_tokens=self.config.max_reasoning_tokens,
            )

            action = self._parse_action(response)

            if action is None:
                return self._extract_final(response)

            if action["type"] == "reason":
                self.context_manager.add("assistant", response)
                continue

            if action["type"] == "tool":
                if tool_calls >= self.config.max_tool_calls_per_turn:
                    return "Maximum tool calls reached."
                tool_calls += 1
                result = self._execute_tool(action, turn)
                self._emit("tool_result", result=result)
                self.context_manager.add("assistant", f"Tool: {action['tool']}")
                self.context_manager.add("tool", result.to_dict())
                if next_step:
                    status = StepStatus.COMPLETED if result.success else StepStatus.FAILED
                    self.planner.mark_step(next_step.step_id, status, result=result.to_dict(), error=result.error)

                if plan and plan.current_step:
                    turn.phase = AgentPhase.PLANNING
                elif result.success:
                    turn.phase = AgentPhase.OBSERVING
                continue

            if action["type"] == "final":
                return action["content"]

        return "Maximum iterations reached."

    def _maybe_plan(self, user_input: str, turn: TurnState) -> Optional[Plan]:
        if not self.config.enable_planning:
            return None
        user_lower = user_input.lower()
        plan_triggers = [
            "first", "then", "step", "plan", "multi-step", "sequence",
            "first do", "start by", "begin by", "create a plan",
            "list of tasks", "multiple things",
        ]
        if not any(t in user_lower for t in plan_triggers):
            return None

        turn.phase = AgentPhase.PLANNING
        self._emit("plan_start", input=user_input)
        plan = self.planner.decompose(user_input)
        turn.plan = [s.to_dict() for s in plan.steps]
        self._emit("plan_created", plan=plan)
        logger.info(f"Plan created: {plan.goal} ({len(plan.steps)} steps)")
        return plan

    def _execute_tool(self, action: dict[str, Any], turn: TurnState) -> ToolResult:
        tool_name = action.get("tool", "")
        params = action.get("params", {})
        turn.phase = AgentPhase.ACTING
        self._emit("tool_start", tool=tool_name, params=params)
        result = self.tools.execute(tool_name, **params)
        turn.record_tool(tool_name, params, result, result.duration_ms)
        self._emit("tool_end", result=result)
        return result

    def _parse_action(self, response: str) -> Optional[dict[str, Any]]:
        text = response.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        for wrapper in ["```json", "```"]:
            if wrapper in text:
                inner = text.split(wrapper)[1].split("```")[0].strip()
                try:
                    parsed = json.loads(inner)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    break

        patterns = {
            "tool": '"type": "tool"',
            "final": '"type": "final"',
            "reason": '"type": "reason"',
            "action": '"type": "action"',
        }

        for action_type, marker in patterns.items():
            if marker in text:
                try:
                    start = text.index("{")
                    depth = 0
                    for i in range(start, len(text)):
                        if text[i] == "{":
                            depth += 1
                        elif text[i] == "}":
                            depth -= 1
                            if depth == 0:
                                obj = json.loads(text[start:i+1])
                                return obj
                except (ValueError, json.JSONDecodeError):
                    continue

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            try:
                parsed = json.loads(text[first_brace:last_brace+1])
                if isinstance(parsed, dict) and "type" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _extract_final(self, response: str) -> str:
        parsed = self._parse_action(response)
        if parsed and parsed.get("type") == "final":
            return parsed.get("content", response)
        return response

    def _build_prompt_context(self, user_input: str, turn: TurnState, next_step: Optional[PlanStep]) -> str:
        parts = [f"User: {user_input}"]

        state_summary = self.context.awareness_prompt()
        parts.append(state_summary)

        context_block = self.context_manager.structured().to_prompt_block()
        if context_block.strip():
            parts.append(context_block)

        if next_step:
            parts.append(f"[Plan: Executing step {next_step.step_id} - {next_step.description}]")
            deps = next_step.depends_on
            if deps:
                plan = self.planner.get_plan()
                if plan:
                    dep_steps = [s for s in plan.steps if s.step_id in deps]
                    for ds in dep_steps:
                        parts.append(f"  Dependency {ds.step_id}: {ds.status.value}")

        available = [t for t in self.tools.list_tools() if t.enabled]
        if available:
            tools_block = "\n".join(
                f"  {t.name}: {t.description} -> {', '.join(p.name for p in t.parameters)}"
                for t in available[:15]
            )
            parts.append(f"Tools:\n{tools_block}")

        parts.append(
            "\nRespond with JSON: {\"type\": \"reason\", \"thought\": \"...\"} to think, "
            "{\"type\": \"tool\", \"tool\": \"name\", \"params\": {...}} to call a tool, "
            "or {\"type\": \"final\", \"content\": \"...\"} when done."
        )

        return "\n\n".join(parts)

    def _build_system_prompt(self) -> str:
        return self.context_manager.system_prompt()

    # ── Session Lifecycle ─────────────────────────────────────

    def start_session(self):
        import uuid
        self._running = True
        s = self.context.session
        s.session_id = str(uuid.uuid4())
        s.started_at = time.time()
        s.current_phase = AgentPhase.IDLE
        self._emit("session_start", session=s)
        logger.info(f"Session started: {s.session_id[:8]}")

    def finish_session(self):
        self._running = False
        s = self.context.session
        s.finish_turn()
        self._emit("session_end", session=s)
        logger.info(f"Session ended: {s.session_id[:8]} ({s.turn_count} turns)")

    def _finish_turn(self, turn: TurnState, output: str):
        self.context.session.finish_turn(output)
        self.context_manager.add("assistant", output)
        self.context.add_turn_context(turn)
        self._emit("turn_end", turn=turn)

    def on_wake(self, confidence: float = 0.0, wake_word: str = "nexi"):
        s = self.context.session
        s.wake_count += 1
        s.wake_confidence = confidence
        s.wake_word = wake_word
        s.current_phase = AgentPhase.THINKING
        self._emit("wake_detected", confidence=confidence, wake_word=wake_word)

    def on_sleep(self):
        self.context.session.current_phase = AgentPhase.IDLE
        self._emit("sleep")

    def identify_user(self, identity: str):
        s = self.context.session
        s.user_identified = True
        s.user_identity = identity
        self.context.add_context("user_identity", identity)

    # ── Introspection ─────────────────────────────────────────

    def manifest(self) -> dict[str, Any]:
        tools = self.tools.capabilities_manifest()
        return {
            "name": "Nexi",
            "version": "1.0.0",
            "description": "Autonomous AI assistant with think→act→observe loop",
            "tools": tools,
            "tool_count": len(tools),
            "config": self.config.to_dict(),
            "session": self.context.session.to_dict(),
            "planning": self.config.enable_planning,
            "type": "agent",
            "protocol": "nex-agent-v1",
        }

    def status_report(self) -> str:
        s = self.context.session
        lines = [
            f"Nexi Agent Status",
            f"{'='*50}",
            f"Session: {s.session_id[:8] or 'none'}",
            f"Phase: {s.current_phase.value}",
            f"Turns: {s.turn_count}",
            f"Wakes: {s.wake_count}",
            f"Errors: {s.consecutive_failures} consecutive",
            f"Duration: {round(s.total_duration_s)}s",
            f"Tools: {self.tools.count()} registered",
            f"Planning: {'enabled' if self.config.enable_planning else 'disabled'}",
            f"Context: {self.context_manager.message_count()} messages, ~{self.context_manager.token_count()} tokens",
        ]
        plan = self.planner.get_plan()
        if plan:
            lines.append(f"\nActive Plan:\n{plan.summary()}")
        return "\n".join(lines)
