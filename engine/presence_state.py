from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


_MODE_BY_STATE = {
    "sleep": "sleeping",
    "online": "online",
    "listening": "listening",
    "waiting_for_speech": "listening",
    "recognising": "listening",
    "thinking": "thinking",
    "saying": "speaking",
    "error": "error",
}

_ATTENTION_BY_STATE = {
    "sleep": "none",
    "online": "audio",
    "listening": "user",
    "waiting_for_speech": "user",
    "recognising": "audio",
    "thinking": "tool",
    "saying": "user",
    "error": "system",
}

_GOAL_BY_STATE = {
    "sleep": "waiting for wake word",
    "online": "wake detected",
    "listening": "waiting for user command",
    "waiting_for_speech": "waiting for speech",
    "recognising": "recognising speech",
    "thinking": "processing command",
    "saying": "speaking response",
    "error": "handling error",
}


@dataclass
class PresenceState:
    mode: str = "sleeping"
    attention: str = "none"
    confidence: float = 0.0
    energy: str = "normal"
    last_event: str = "initialised"
    current_goal: str = "waiting for wake word"
    memory_context: str = ""
    tone: str = "calm"
    session_id: str = ""
    updated_at: float = field(default_factory=time.time)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def update_mode(
        self,
        mode: str,
        *,
        attention: str | None = None,
        confidence: float | None = None,
        energy: str | None = None,
        current_goal: str | None = None,
        memory_context: str | None = None,
        last_event: str | None = None,
        session_id: str | None = None,
    ) -> None:
        with self._lock:
            if mode:
                self.mode = str(mode).strip().lower() or self.mode
            if attention is not None:
                self.attention = str(attention).strip().lower() or "none"
            if confidence is not None:
                self.confidence = max(0.0, min(1.0, float(confidence)))
            if energy is not None:
                self.energy = str(energy).strip().lower() or "normal"
            if current_goal is not None:
                self.current_goal = str(current_goal).strip() or self.current_goal
            if memory_context is not None:
                self.memory_context = str(memory_context).strip()[:240]
            if last_event is not None:
                self.last_event = str(last_event).strip() or self.last_event
            if session_id is not None:
                self.session_id = str(session_id).strip()
            self.updated_at = time.time()

    def update_from_ui_state(
        self,
        state: str,
        *,
        source: str = "system",
        status: str = "",
        text: str = "",
        session_id: str = "",
    ) -> None:
        raw_state = (state or "sleep").strip().lower()
        mode = _MODE_BY_STATE.get(raw_state, "sleeping")
        attention = _ATTENTION_BY_STATE.get(raw_state, "none")
        goal = _GOAL_BY_STATE.get(raw_state, "waiting for wake word")
        detail = (text or "").strip()
        if detail and raw_state in {"thinking", "recognising"}:
            goal = f"{goal}: {detail[:80]}"
        self.update_mode(
            mode,
            attention=attention,
            current_goal=goal,
            last_event=(status or raw_state),
            session_id=session_id,
        )

    def update_attention(self, attention: str) -> None:
        self.update_mode(self.mode, attention=attention)

    def update_confidence(self, confidence: float) -> None:
        self.update_mode(self.mode, confidence=confidence)

    def set_goal(self, goal: str, detail: str = "") -> None:
        value = str(goal or "").strip()
        if detail:
            value = f"{value}: {str(detail).strip()[:120]}"
        self.update_mode(self.mode, current_goal=value)

    def set_tone(self, tone: str) -> None:
        value = str(tone or "calm").strip().lower() or "calm"
        with self._lock:
            self.tone = value[:40]
            self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "attention": self.attention,
                "confidence": self.confidence,
                "energy": self.energy,
                "last_event": self.last_event,
                "current_goal": self.current_goal,
                "memory_context": self.memory_context,
                "tone": self.tone,
                "session_id": self.session_id,
                "updated_at": self.updated_at,
            }

    def to_ui_string(self) -> str:
        data = self.to_dict()
        return (
            f"ATTENTION: {data['attention'].upper()}\n"
            f"GOAL: {data['current_goal'].upper()}\n"
            f"CONFIDENCE: {int(data['confidence'] * 100)}%\n"
            f"ENERGY: {data['energy'].upper()}"
        )

    def to_llm_context(self) -> str:
        data = self.to_dict()
        return (
            "Nexi internal state:\n"
            f"- mode: {data['mode']}\n"
            f"- attention: {data['attention']}\n"
            f"- confidence: {data['confidence']:.2f}\n"
            f"- goal: {data['current_goal']}\n"
            f"- last_event: {data['last_event']}"
        )

    def reset(self) -> None:
        with self._lock:
            self.mode = "sleeping"
            self.attention = "none"
            self.confidence = 0.0
            self.energy = "normal"
            self.last_event = "reset"
            self.current_goal = "waiting for wake word"
            self.memory_context = ""
            self.tone = "calm"
            self.session_id = ""
            self.updated_at = time.time()


_presence = PresenceState()


def get_presence() -> PresenceState:
    return _presence


def get_presence_state() -> dict[str, Any]:
    return _presence.to_dict()


def reset_presence_state() -> None:
    _presence.reset()
