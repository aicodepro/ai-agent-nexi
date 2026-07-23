from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class AgentPhase(str, Enum):
    INIT = "init"
    IDLE = "idle"
    THINKING = "thinking"
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    SPEAKING = "speaking"
    WAITING = "waiting"
    ERROR = "error"
    DONE = "done"


@dataclass
class TurnState:
    turn_id: int = 0
    phase: AgentPhase = AgentPhase.INIT
    started_at: float = 0.0
    finished_at: float = 0.0
    user_input: str = ""
    assistant_output: str = ""
    plan: Optional[list[dict[str, Any]]] = None
    plan_index: int = 0
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def duration_s(self) -> float:
        if self.finished_at > 0:
            return self.finished_at - self.started_at
        return time.time() - self.started_at


@dataclass
class SessionState:
    session_id: str = ""
    started_at: float = 0.0
    wake_count: int = 0
    turn_count: int = 0
    consecutive_failures: int = 0
    current_phase: AgentPhase = AgentPhase.IDLE
    wake_word: str = ""
    wake_confidence: float = 0.0
    user_identified: bool = False
    user_identity: str = ""
    current_turn: TurnState = field(default_factory=TurnState)
    turn_history: list[TurnState] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def new_turn(self, user_input: str = "") -> TurnState:
        self.turn_count += 1
        turn = TurnState(
            turn_id=self.turn_count,
            phase=AgentPhase.THINKING,
            started_at=time.time(),
            user_input=user_input,
        )
        self.current_turn = turn
        return turn

    def finish_turn(self, output: str = ""):
        self.current_turn.finished_at = time.time()
        self.current_turn.assistant_output = output
        self.current_turn.phase = AgentPhase.DONE
        self.turn_history.append(self.current_turn)
        self.current_phase = AgentPhase.IDLE

    def record_tool(self, name: str, params: dict[str, Any], result: Any, duration_ms: float):
        self.current_turn.tools_used.append({
            "name": name,
            "params": params,
            "duration_ms": duration_ms,
            "success": getattr(result, "success", True),
        })

    def record_error(self, error: str):
        self.current_turn.errors.append(error)
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.current_phase = AgentPhase.ERROR

    @property
    def total_duration_s(self) -> float:
        return time.time() - self.started_at

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "duration_s": round(self.total_duration_s, 1),
            "turns": self.turn_count,
            "wakes": self.wake_count,
            "consecutive_failures": self.consecutive_failures,
            "phase": self.current_phase.value,
            "user": self.user_identity or "unknown",
            "last_turn": {
                "input": self.current_turn.user_input[:200] if self.current_turn else "",
                "tools": len(self.current_turn.tools_used) if self.current_turn else 0,
                "duration_s": round(self.current_turn.duration_s, 1) if self.current_turn else 0,
            } if self.current_turn else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "wake_count": self.wake_count,
            "turn_count": self.turn_count,
            "phase": self.current_phase.value,
            "user_identified": self.user_identified,
            "user_identity": self.user_identity,
            "total_duration_s": round(self.total_duration_s, 1),
        }


class AgentContext:
    def __init__(self):
        self.session = SessionState()
        self._knowledge_base: dict[str, str] = {}
        self._recent_context: list[dict[str, Any]] = []
        self._max_context_turns = 20

    def add_context(self, key: str, value: str):
        self._knowledge_base[key] = value

    def get_context(self, key: str, default: str = "") -> str:
        return self._knowledge_base.get(key, default)

    def add_turn_context(self, turn: TurnState):
        self._recent_context.append({
            "role": "user",
            "content": turn.user_input,
        })
        self._recent_context.append({
            "role": "assistant",
            "content": turn.assistant_output,
        })
        if len(self._recent_context) > self._max_context_turns * 2:
            self._recent_context = self._recent_context[-self._max_context_turns * 2:]

    def context_window(self, max_tokens: int = 4000) -> list[dict[str, str]]:
        return self._recent_context[-max_tokens // 2:]

    def reset(self):
        self.session = SessionState()
        self._knowledge_base.clear()
        self._recent_context.clear()

    def awareness_prompt(self) -> str:
        s = self.session
        t = s.current_turn
        parts = [
            f"[Session: {s.session_id[:8]} | Turns: {s.turn_count} | Phase: {s.current_phase.value}]",
            f"[User: {s.user_identity or 'unknown'} | Duration: {round(s.total_duration_s)}s]",
        ]
        if t.tools_used:
            tools_summary = ", ".join(f"{x['name']}({round(x['duration_ms'])}ms)" for x in t.tools_used[-3:])
            parts.append(f"[Tools this turn: {tools_summary}]")
        if s.consecutive_failures > 0:
            parts.append(f"[WARNING: {s.consecutive_failures} consecutive failures]")
        return " | ".join(parts)
