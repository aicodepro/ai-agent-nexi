from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any


CANONICAL_STATES = {
    "sleep",
    "online",
    "listening",
    "waiting_for_speech",
    "recognising",
    "thinking",
    "saying",
    "error",
}

STATE_ALIASES = {
    "idle": "sleep",
    "sleeping": "sleep",
    "wake_detected": "online",
    "wake": "online",
    "hotword_detected": "online",
    "double_clap_detected": "online",
    "clap_detected": "online",
    "listening_started": "listening",
    "listening": "listening",
    "speech_started": "recognising",
    "speech_ended": "recognising",
    # No speech was captured, so there is nothing to recognise. Staying on
    # "listening" keeps the announced state truthful; the session_finish that
    # follows moves it to sleep.
    "no_speech_timeout": "listening",
    "transcribing": "recognising",
    "asr_started": "recognising",
    "asr_result": "thinking",
    "command_started": "thinking",
    "speaking": "saying",
    "tts_started": "saying",
    "tts_done": "sleep",
    "checking_files": "thinking",
    "running_tool": "thinking",
    "searching": "thinking",
    "react_thinking": "thinking",
    "react_tool_start": "thinking",
    "react_tool_end": "thinking",
}

STATE_LABELS = {
    "sleep": "SLEEPING",
    "online": "ONLINE",
    "listening": "LISTENING",
    "waiting_for_speech": "LISTENING",
    "recognising": "RECOGNISING",
    "thinking": "THINKING",
    "saying": "SAYING",
    "error": "ERROR",
}


def canonical_state(state: str) -> str:
    raw = (state or "sleep").strip().lower()
    raw = STATE_ALIASES.get(raw, raw)
    return raw if raw in CANONICAL_STATES else "sleep"


def label_for(state: str, source: str = "") -> str:
    canonical = canonical_state(state)
    return STATE_LABELS[canonical]


def log_for(state: str, source: str = "", text: str = "") -> tuple[str, str]:
    canonical = canonical_state(state)
    src = (source or "").strip().lower()
    if canonical == "online":
        if src == "hotword":
            return "wake", "WAKE: Hotword detected"
        if src in {"clap", "double_clap", "double-clap", "double clap"}:
            return "wake", "WAKE: Double clap detected"
        return "wake", "WAKE: Wake detected"
    if canonical == "listening":
        return "sys", "SYS: Listening..."
    if canonical == "waiting_for_speech":
        return "sys", "SYS: Waiting for speech..."
    if canonical == "recognising":
        return "sys", "SYS: Recognising speech..."
    if canonical == "thinking":
        return "sys", "SYS: Thinking..."
    if canonical == "saying":
        return "sys", "SYS: Saying..."
    if canonical == "sleep":
        return "sys", "SYS: Sleep mode"
    if canonical == "error":
        return "err", f"SYS: Error{(': ' + text[:80]) if text else ''}"
    return "sys", STATE_LABELS[canonical]


@dataclass
class UIStateEvent:
    state: str
    source: str
    text: str
    status: str
    label: str
    log_level: str
    log_message: str
    created_at: float
    sequence: int
    session_id: str = ""
    session_epoch: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        from engine.accessibility_feedback import earcon_for_state

        payload = {
            "state": self.state,
            "source": self.source,
            "text": self.text,
            "status": self.status,
            "message": self.label,
            "label": self.label,
            "log_level": self.log_level,
            "log": self.log_message,
            "created_at": self.created_at,
            "sequence": self.sequence,
            "session_id": self.session_id,
            "session_epoch": self.session_epoch,
            "earcon": earcon_for_state(self.state),
        }
        try:
            from engine.presence_state import get_presence_state
            payload["presence"] = get_presence_state()
        except Exception:
            pass
        return payload


class UIStateManager:
    """Canonical Python-side UI state emitter with small dedupe window."""

    def __init__(self, *, dedupe_ms: int = 250):
        self.dedupe_ms = max(0, int(dedupe_ms))
        self._last_key: tuple[str, float, str, str, str] | None = None
        self._last_emit_at = 0.0
        self._sequence_lock = threading.Lock()
        self._session_sequences: dict[tuple[str, float], int] = {}
        self.events: list[UIStateEvent] = []
        self._ack_watch_lock = threading.Lock()
        self._ack_watch_keys: set[str] = set()

    def emit(
        self,
        state: str,
        *,
        source: str = "system",
        text: str = "",
        status: str = "",
        session_id: str = "",
        session_epoch: float = 0.0,
        force: bool = False,
    ) -> UIStateEvent | None:
        canonical = canonical_state(state)
        safe_source = (source or "system").strip() or "system"
        safe_text = (text or "")[:120]
        safe_status = (status or canonical).strip() or canonical
        safe_session_id = session_id or ""
        safe_session_epoch = float(session_epoch or 0.0)
        key = (safe_session_id, safe_session_epoch, canonical, safe_source, safe_status)
        now = time.time()
        if not force and self._last_key == key and (now - self._last_emit_at) * 1000.0 < self.dedupe_ms:
            return None

        level, message = log_for(canonical, safe_source, safe_text)
        with self._sequence_lock:
            sequence_key = (safe_session_id, safe_session_epoch)
            sequence = self._session_sequences.get(sequence_key, 0) + 1
            self._session_sequences[sequence_key] = sequence
        event = UIStateEvent(
            state=canonical,
            source=safe_source,
            text=safe_text,
            status=safe_status,
            label=label_for(canonical, safe_source),
            log_level=level,
            log_message=message,
            created_at=now,
            sequence=sequence,
            session_id=safe_session_id,
            session_epoch=safe_session_epoch,
        )
        self._last_key = key
        self._last_emit_at = now
        self.events.append(event)
        try:
            from engine.accessibility_feedback import play_earcon

            play_earcon(canonical)
        except Exception:
            pass
        # Acknowledge the durable capture request. The audio process only emits
        # these once it has really taken the microphone, so this - not the act of
        # asking - is what closes out FOLLOWUP_REQUESTED/QUEUED.
        try:
            from engine.dialogue_context import CaptureState, set_capture_state
            _capture_ack = {
                "listening_started": CaptureState.CAPTURE_STARTED,
                "speech_started": CaptureState.SPEECH_STARTED,
                "asr_result": CaptureState.COMPLETED,
                "no_speech_timeout": CaptureState.NO_SPEECH,
            }.get(safe_status.lower())
            if _capture_ack is not None:
                set_capture_state(_capture_ack, reason=safe_status.lower())
        except Exception:
            pass
        # Drive the strict voice state machine from the canonical UI state so the
        # command-acceptance gate always reflects the real lifecycle.
        try:
            from engine.voice_state_machine import get_voice_state_machine
            _status_event = {
                "wake_detected": "wake_detected",
                "listening": "listening_started",
                "listening_started": "listening_started",
                "waiting_for_speech": "listening_started",
                "speech_started": "speech_started",
                "speech_ended": "speech_ended",
                "no_speech_timeout": "no_speech_timeout",
                "asr_started": "asr_started",
                "asr_result": "asr_result",
                "speaking_started": "tts_started",
                "idle": "session_finish",
                "sleeping": "session_finish",
            }.get(safe_status.lower())
            if safe_status.lower() == "asr_result" and canonical == "recognising":
                _status_event = "asr_started"
            _vsm_event = _status_event or {
                "online": "wake_detected",
                "listening": "listening_started",
                "waiting_for_speech": "listening_started",
                "recognising": "asr_started",
                "thinking": "command_started",
                "saying": "tts_started",
                "sleep": "session_finish",
                "error": "error",
            }.get(canonical)
            if _vsm_event:
                get_voice_state_machine().transition(_vsm_event, source=safe_source, session_id=session_id or "")
        except Exception:
            pass
        try:
            from engine.presence_state import get_presence
            get_presence().update_from_ui_state(
                canonical,
                source=safe_source,
                text=safe_text,
                status=safe_status,
                session_id=session_id or "",
            )
        except Exception:
            pass
        self._post_to_eel(event)
        print(f'[UI_SEND] state={canonical} label={event.label} source={safe_source} session={event.session_id} sequence={event.sequence}', flush=True)
        return event

    def _post_to_eel(self, event: UIStateEvent) -> bool:
        try:
            import eel
            payload = event.to_payload()
            eel.updateNexiState(payload)
            try:
                eel.updatePresence(payload.get("presence", {}))
            except Exception:
                pass
            self._watch_for_ack(event)
            return True
        except AttributeError:
            return False
        except Exception:
            return False

    def _watch_for_ack(self, event: UIStateEvent) -> None:
        if not event.session_id:
            return
        key = f"{event.session_id}|{event.state}|{event.sequence}"
        with self._ack_watch_lock:
            if key in self._ack_watch_keys:
                return
            self._ack_watch_keys.add(key)

        def _wait() -> None:
            try:
                from engine.ui_state_ack import wait_for_ack
                if not wait_for_ack(event.state, event.session_id, event.sequence, timeout_ms=2000):
                    print(f"[UI_ACK_MISSING] state={event.state} session={event.session_id} sequence={event.sequence}", flush=True)
            except Exception:
                print(f"[UI_ACK_MISSING] state={event.state} session={event.session_id} sequence={event.sequence}", flush=True)
            finally:
                with self._ack_watch_lock:
                    self._ack_watch_keys.discard(key)

        threading.Thread(target=_wait, daemon=True, name="ui-ack-watch").start()

    def sleep(self, source: str = "system") -> UIStateEvent | None:
        return self.emit("sleep", source=source)

    def online(self, source: str = "system") -> UIStateEvent | None:
        return self.emit("online", source=source)

    def listening(self, source: str = "system") -> UIStateEvent | None:
        return self.emit("listening", source=source)

    def recognising(self, source: str = "system") -> UIStateEvent | None:
        return self.emit("recognising", source=source)

    def reset(self) -> None:
        self._last_key = None
        self._last_emit_at = 0.0
        with self._sequence_lock:
            self._session_sequences.clear()
        self.events.clear()
        try:
            from engine.presence_state import reset_presence_state
            reset_presence_state()
        except Exception:
            pass


_manager = UIStateManager()


def get_ui_state_manager() -> UIStateManager:
    return _manager


def emit_state(state: str, *, source: str = "system", text: str = "", status: str = "", session_id: str = "", session_epoch: float = 0.0, force: bool = False) -> UIStateEvent | None:
    return _manager.emit(state, source=source, text=text, status=status, session_id=session_id, session_epoch=session_epoch, force=force)
