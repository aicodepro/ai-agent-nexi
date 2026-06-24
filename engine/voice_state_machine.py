"""
Strict voice lifecycle state machine for Nexi.

The state machine is intentionally small and explicit: it gates full voice
commands, permits only hotword/interrupt handling during TTS, records live
transition diagnostics, and exposes compatibility constants used by older tests.
"""

from __future__ import annotations

import os
import re
import time
from enum import Enum
from typing import Any

POST_TTS_COOLDOWN_MS = 800
BARGE_IN_WORDS = ["stop", "pause", "cancel", "sleep"]
MAX_STATE_HISTORY = 50

VOICE_STATE_CONFIG = {
    "POST_TTS_COOLDOWN_MS": int(os.getenv("NEXI_POST_TTS_COOLDOWN_MS", str(POST_TTS_COOLDOWN_MS))),
    "BARGE_IN_WORDS": [w.strip().lower() for w in os.getenv("NEXI_BARGE_IN_WORDS", ",".join(BARGE_IN_WORDS)).split(",") if w.strip()],
}


class VoiceState(Enum):
    SLEEPING = "sleeping"
    LISTENING = "listening"
    RECORDING_UTTERANCE = "recording_utterance"
    RECOGNIZING = "recognizing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    COOLDOWN = "cooldown"
    ERROR = "error"

    def to_ui_state(self) -> str:
        return {
            VoiceState.SLEEPING: "sleep",
            VoiceState.LISTENING: "listening",
            VoiceState.RECORDING_UTTERANCE: "recognising",
            VoiceState.RECOGNIZING: "recognising",
            VoiceState.THINKING: "thinking",
            VoiceState.SPEAKING: "saying",
            VoiceState.COOLDOWN: "sleep",
            VoiceState.ERROR: "error",
        }.get(self, "sleep")

    @classmethod
    def from_ui_state(cls, ui_state: str) -> "VoiceState":
        return {
            "sleep": VoiceState.SLEEPING,
            "sleeping": VoiceState.SLEEPING,
            "online": VoiceState.LISTENING,
            "listening": VoiceState.LISTENING,
            "waiting_for_speech": VoiceState.LISTENING,
            "recognising": VoiceState.RECOGNIZING,
            "recognizing": VoiceState.RECOGNIZING,
            "thinking": VoiceState.THINKING,
            "saying": VoiceState.SPEAKING,
            "speaking": VoiceState.SPEAKING,
            "cooldown": VoiceState.COOLDOWN,
            "error": VoiceState.ERROR,
        }.get((ui_state or "").strip().lower(), VoiceState.SLEEPING)


# Backwards-compatible string constants expected by existing tests/callers.
SLEEPING = VoiceState.SLEEPING.value
LISTENING = VoiceState.LISTENING.value
RECORDING_UTTERANCE = VoiceState.RECORDING_UTTERANCE.value
RECOGNIZING = VoiceState.RECOGNIZING.value
THINKING = VoiceState.THINKING.value
SPEAKING = VoiceState.SPEAKING.value
COOLDOWN = VoiceState.COOLDOWN.value
ERROR = VoiceState.ERROR.value

HOTWORD_DETECTED_DURING_SPEAKING = "hotword_detected_during_speaking"
TTS_INTERRUPTED_BY_HOTWORD = "tts_interrupted_by_hotword"
INTERRUPT_WORD_DETECTED = "interrupt_word_detected"
BARGE_IN_LISTENING_STARTED = "barge_in_listening_started"
BARGE_IN_COMMAND_CAPTURE_STARTED = "barge_in_command_capture_started"
BARGE_IN_COMMAND_FINALIZED = "barge_in_command_finalized"
AUDIO_BUFFER_FLUSHED = "audio_buffer_flushed"
COOLDOWN_COMPLETE = "cooldown_complete"


class VoiceStateTransition:
    def __init__(
        self,
        from_state: VoiceState,
        to_state: VoiceState,
        event: str,
        condition: str | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "",
        session_id: str = "",
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.event = event
        self.condition = condition
        self.metadata = metadata or {}
        self.source = source
        self.session_id = session_id
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "state_before": self.from_state.value,
            "event": self.event,
            "state_after": self.to_state.value,
            "source": self.source,
            "session_id": self.session_id,
            "metadata": dict(self.metadata),
        }


class VoiceStateMachine:
    def __init__(self, session_id: str | None = None):
        self.config = VOICE_STATE_CONFIG.copy()
        self._session_id = session_id
        self.reset(session_id=session_id)

    def reset(self, session_id: str | None = None) -> None:
        self._state = VoiceState.SLEEPING
        self._session_id = session_id if session_id is not None else self._session_id
        self._state_history: list[VoiceState] = [VoiceState.SLEEPING]
        self._transition_history: list[VoiceStateTransition] = []
        self._interrupt_requested = False
        self._interrupt_reason = ""
        self._last_interruption_reason = ""
        self._last_ignored_voice_event_reason = ""
        self._last_transcript = ""
        self._cooldown_until = 0.0
        try:
            from engine.interrupt_controller import set_speaking, clear_interrupt
            set_speaking(False)
            clear_interrupt()
        except Exception:
            pass

    def get_state(self) -> str:
        return self._state.value

    def get_voice_state(self) -> VoiceState:
        return self._state

    def transition(self, event: str, source: str = "", metadata: dict[str, Any] | None = None, session_id: str | None = None) -> str:
        event = (event or "").strip().lower()
        if session_id:
            self._session_id = session_id
        if self._is_in_cooldown() and event not in {COOLDOWN_COMPLETE, "session_finish", "sleep", "error", "recovered"}:
            self.record_ignored_voice_event(f"cooldown:{event}")
            print(f"[VOICE_STATE] transition_failed reason=cooldown event={event}", flush=True)
            return self._state.value

        old_state = self._state
        new_state = self._next_state(event)
        if new_state is None:
            print(f"[VOICE_STATE] transition_failed reason=no_valid_transition event={event} current={self._state.value}", flush=True)
            return self._state.value

        self._state = new_state
        self._state_history.append(self._state)
        if len(self._state_history) > MAX_STATE_HISTORY:
            self._state_history = self._state_history[-MAX_STATE_HISTORY:]

        transition = VoiceStateTransition(old_state, self._state, event, metadata=metadata, source=source, session_id=self._session_id or "")
        self._transition_history.append(transition)
        if len(self._transition_history) > MAX_STATE_HISTORY:
            self._transition_history = self._transition_history[-MAX_STATE_HISTORY:]

        if self._state == VoiceState.SPEAKING:
            self._on_enter_speaking()
        elif self._state == VoiceState.COOLDOWN:
            self._on_enter_cooldown()
        elif self._state == VoiceState.SLEEPING:
            self._on_enter_sleeping()
        elif self._state == VoiceState.LISTENING and event == BARGE_IN_LISTENING_STARTED:
            self._clear_cooldown()

        print(f"[VOICE_STATE] {old_state.value} -> {self._state.value} event={event} source={source}", flush=True)
        return self._state.value

    def _next_state(self, event: str) -> VoiceState | None:
        if event in {"sleep", "session_finish"}:
            return VoiceState.SLEEPING
        if event == "error":
            return VoiceState.ERROR
        if self._state == VoiceState.ERROR and event in {"recovered", "session_finish"}:
            return VoiceState.SLEEPING

        table = {
            (VoiceState.SLEEPING, "wake_detected"): VoiceState.LISTENING,
            (VoiceState.SLEEPING, "clap_detected"): VoiceState.LISTENING,
            (VoiceState.SLEEPING, "hotkey_detected"): VoiceState.LISTENING,
            (VoiceState.SLEEPING, "ui_button_pressed"): VoiceState.LISTENING,
            (VoiceState.LISTENING, "listening_started"): VoiceState.LISTENING,
            (VoiceState.LISTENING, "speech_started"): VoiceState.RECORDING_UTTERANCE,
            (VoiceState.LISTENING, "asr_started"): VoiceState.RECOGNIZING,
            (VoiceState.LISTENING, BARGE_IN_COMMAND_CAPTURE_STARTED): VoiceState.RECORDING_UTTERANCE,
            (VoiceState.RECORDING_UTTERANCE, "speech_ended"): VoiceState.RECOGNIZING,
            (VoiceState.RECORDING_UTTERANCE, "asr_started"): VoiceState.RECOGNIZING,
            (VoiceState.RECORDING_UTTERANCE, BARGE_IN_COMMAND_FINALIZED): VoiceState.RECOGNIZING,
            (VoiceState.RECOGNIZING, "asr_result"): VoiceState.THINKING,
            (VoiceState.RECOGNIZING, "intent_routed"): VoiceState.THINKING,
            (VoiceState.RECOGNIZING, "command_started"): VoiceState.THINKING,
            (VoiceState.SLEEPING, "command_started"): VoiceState.THINKING,
            (VoiceState.LISTENING, "command_started"): VoiceState.THINKING,
            (VoiceState.THINKING, "command_started"): VoiceState.THINKING,
            (VoiceState.SLEEPING, "tts_started"): VoiceState.SPEAKING,
            (VoiceState.LISTENING, "tts_started"): VoiceState.SPEAKING,
            (VoiceState.RECOGNIZING, "tts_started"): VoiceState.SPEAKING,
            (VoiceState.THINKING, "tts_started"): VoiceState.SPEAKING,
            (VoiceState.SPEAKING, "tts_finished"): VoiceState.COOLDOWN,
            (VoiceState.SPEAKING, "interrupted"): VoiceState.COOLDOWN,
            (VoiceState.SPEAKING, HOTWORD_DETECTED_DURING_SPEAKING): VoiceState.SPEAKING,
            (VoiceState.SPEAKING, TTS_INTERRUPTED_BY_HOTWORD): VoiceState.COOLDOWN,
            (VoiceState.SPEAKING, INTERRUPT_WORD_DETECTED): VoiceState.COOLDOWN,
            (VoiceState.COOLDOWN, COOLDOWN_COMPLETE): VoiceState.SLEEPING,
            (VoiceState.COOLDOWN, "wake_during_cooldown"): VoiceState.LISTENING,
            (VoiceState.COOLDOWN, BARGE_IN_LISTENING_STARTED): VoiceState.LISTENING,
        }
        # Explicit barge-in path can move SPEAKING/COOLDOWN into LISTENING after TTS is stopped/flushed.
        if event == BARGE_IN_LISTENING_STARTED and self._state in {VoiceState.SPEAKING, VoiceState.COOLDOWN}:
            return VoiceState.LISTENING
        return table.get((self._state, event))

    def can_accept_full_command(self, source: str = "") -> bool:
        if self._state in {VoiceState.LISTENING, VoiceState.RECORDING_UTTERANCE}:
            return True
        self.record_ignored_voice_event(f"state={self._state.value}")
        print(f"[VOICE_STATE] can_accept_full_command=false state={self._state.value} source={source}", flush=True)
        return False

    def can_accept_interrupt(self, word: str = "") -> bool:
        if self._state != VoiceState.SPEAKING:
            return False
        if not word:
            return True
        return self.is_interrupt_word(word)

    def is_interrupt_word(self, word: str) -> bool:
        text = re.sub(r"[^a-z\s]", " ", (word or "").lower())
        tokens = set(text.split())
        return any(w in tokens for w in self.config["BARGE_IN_WORDS"])

    def is_hotword_text(self, text: str) -> bool:
        value = re.sub(r"[^a-z\s]", " ", (text or "").lower())
        phrases = [p.strip().lower() for p in os.getenv("NEXI_HOTWORD_PHRASES", os.getenv("NEXI_HOTWORD_PHRASE", "hey nexi,nexi")).split(",") if p.strip()]
        if os.getenv("NEXI_ENABLE_JARBOS_HOTWORD", "false").lower() in {"1", "true", "yes", "on"}:
            phrases.append("jarbos")
        return any(re.search(rf"\b{re.escape(phrase)}\b", value) for phrase in phrases)

    def request_interrupt(self, reason: str = "") -> None:
        self._interrupt_requested = True
        self._interrupt_reason = reason or "interrupt"
        self._last_interruption_reason = self._interrupt_reason

    def clear_interrupt(self) -> None:
        self._interrupt_requested = False
        self._interrupt_reason = ""

    def is_interrupt_requested(self) -> bool:
        return self._interrupt_requested

    def get_interrupt_reason(self) -> str:
        return self._interrupt_reason

    def get_last_interruption_reason(self) -> str:
        return self._last_interruption_reason

    def record_interruption(self, reason: str) -> None:
        self._last_interruption_reason = (reason or "").strip()

    def record_ignored_voice_event(self, reason: str) -> None:
        self._last_ignored_voice_event_reason = (reason or "").strip()

    def get_last_ignored_voice_event_reason(self) -> str:
        return self._last_ignored_voice_event_reason

    def record_transcript(self, transcript: str) -> None:
        self._last_transcript = (transcript or "").strip()[:500]

    def get_last_transcript(self) -> str:
        return self._last_transcript

    def mark_cooldown(self) -> None:
        self._cooldown_until = time.time() + (self.config["POST_TTS_COOLDOWN_MS"] / 1000.0)

    def _clear_cooldown(self) -> None:
        self._cooldown_until = 0.0

    def _is_in_cooldown(self) -> bool:
        return time.time() < self._cooldown_until

    def get_cooldown_remaining_ms(self) -> int:
        return max(0, int((self._cooldown_until - time.time()) * 1000.0))

    def _on_enter_speaking(self) -> None:
        try:
            from engine.interrupt_controller import set_speaking
            set_speaking(True)
        except Exception:
            pass
        # Do not fully stop the mic stream. The wake pipeline keeps a hotword-only
        # path alive while session state is "saying"; full command capture remains gated.

    def _on_enter_cooldown(self) -> None:
        self.clear_interrupt()
        self.mark_cooldown()

    def _on_enter_sleeping(self) -> None:
        self._clear_cooldown()
        try:
            from engine.interrupt_controller import set_speaking
            set_speaking(False)
        except Exception:
            pass
        try:
            from engine.audio_wake_pipeline import resume_detectors
            resume_detectors()
        except Exception:
            pass

    def get_state_history(self, limit: int | None = None) -> list[str]:
        values = self._state_history if limit is None else self._state_history[-limit:]
        return [state.value for state in values]

    def get_last_transition(self) -> dict[str, Any]:
        return self._transition_history[-1].to_dict() if self._transition_history else {}

    def get_previous_state(self) -> str:
        return self._state_history[-2].value if len(self._state_history) >= 2 else ""

    def get_session_id(self) -> str | None:
        return self._session_id

    def update_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "session_id": self._session_id,
            "interrupt_requested": self._interrupt_requested,
            "interrupt_reason": self._interrupt_reason,
            "last_interruption_reason": self._last_interruption_reason,
            "last_ignored_voice_event_reason": self._last_ignored_voice_event_reason,
            "last_transcript": self._last_transcript,
            "cooldown_until": self._cooldown_until,
            "state_history": self.get_state_history(),
            "last_transition": self.get_last_transition(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceStateMachine":
        instance = cls(data.get("session_id"))
        instance._state = VoiceState(data.get("state", VoiceState.SLEEPING.value))
        instance._interrupt_requested = data.get("interrupt_requested", False)
        instance._interrupt_reason = data.get("interrupt_reason", "")
        instance._last_interruption_reason = data.get("last_interruption_reason", "")
        instance._last_ignored_voice_event_reason = data.get("last_ignored_voice_event_reason", "")
        instance._last_transcript = data.get("last_transcript", "")
        instance._cooldown_until = data.get("cooldown_until", 0.0)
        instance._state_history = [VoiceState(s) for s in data.get("state_history", [VoiceState.SLEEPING.value])]
        return instance


_active_state_machine: VoiceStateMachine | None = None


def get_voice_state_machine(session_id: str | None = None) -> VoiceStateMachine:
    global _active_state_machine
    if _active_state_machine is None:
        _active_state_machine = VoiceStateMachine(session_id)
    elif session_id is not None:
        _active_state_machine.update_session_id(session_id)
    return _active_state_machine


def transition_voice_state(event: str, source: str = "", session_id: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    return get_voice_state_machine(session_id).transition(event, source=source, metadata=metadata, session_id=session_id)


def can_accept_full_command(source: str = "") -> bool:
    return get_voice_state_machine().can_accept_full_command(source)


def is_interrupt_word(word: str) -> bool:
    return get_voice_state_machine().is_interrupt_word(word)


def get_current_state() -> str:
    return get_voice_state_machine().get_state()
