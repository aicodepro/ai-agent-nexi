from __future__ import annotations

import os
import threading
import time
import uuid


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


# After an audible response has ended, keep the recovery window short so a lost
# terminal event cannot leave wake detection paused. Pre-speech thinking uses the
# independent 60-second renewable progress timeout below.
_AUTO_FINISH_TIMEOUT_SECONDS = max(1.0, _env_float("NEXI_SESSION_IDLE_TIMEOUT_SECONDS", 3.0))

# Before NEXI has spoken (still thinking / awaiting the bridge's response in the
# other process), allow a renewable 60-second grace so normal long work survives
# while a producer crash still re-arms detectors.
_PRE_SPEECH_GRACE_SECONDS = max(
    60.0,
    _AUTO_FINISH_TIMEOUT_SECONDS,
    _env_float("NEXI_SESSION_PRE_SPEECH_GRACE_SECONDS", 60.0),
)

# When NEXI has ASKED the user something, the 3-second post-speech re-arm is
# wrong: it sleeps before a human can answer, and the timeout path then discards
# the pending question. "Create a folder" -> "What should I name it?" -> asleep
# in 3s made every clarification a dead end. A question deserves a human answer
# window; this is still bounded so a missed answer cannot pin detectors open.
_AWAITING_ANSWER_TIMEOUT_SECONDS = max(
    _AUTO_FINISH_TIMEOUT_SECONDS,
    _env_float("NEXI_SESSION_AWAITING_ANSWER_SECONDS", 20.0),
)


def _question_is_pending() -> bool:
    """True when NEXI asked something and is still awaiting the user's reply."""
    try:
        from engine.clarification_manager import has_pending_clarification
        if has_pending_clarification():
            return True
    except Exception:
        pass
    try:
        from engine.followup_manager import has_pending_followup
        return bool(has_pending_followup())
    except Exception:
        return False

# TTS is a renewable lease, not an unbounded state. Heartbeats may extend the
# soft deadline, but never beyond the hard deadline for one audible response.
_TTS_LEASE_SECONDS = max(1.0, _env_float("NEXI_TTS_LEASE_SECONDS", 15.0))
_TTS_HARD_TIMEOUT_SECONDS = min(
    59.0,
    max(_TTS_LEASE_SECONDS, _env_float("NEXI_TTS_HARD_TIMEOUT_SECONDS", 45.0)),
)

_POST_SESSION_WAKE_SUPPRESS_MS = max(0, _env_int("NEXI_POST_SESSION_WAKE_SUPPRESS_MS", 800))


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


class WakeSessionManager:
    _instance: WakeSessionManager | None = None
    _lock = threading.Lock()

    def __init__(self):
        self._session_id: str | None = None
        self._source: str = ""
        self._state: str = "sleep"
        self._detectors_paused: bool = False
        self._started_at: float = 0.0
        self._last_event_at: float = 0.0
        self._last_finished_at: float = 0.0
        self._has_spoken: bool = False
        self._tts_active: bool = False
        self._tts_cooldown_active: bool = False
        self._last_lifecycle_sequence: int = 0
        self._tts_lease_deadline: float = 0.0
        self._tts_hard_deadline: float = 0.0
        self._tts_producer_id: str = ""
        self._global_tts_lease_id: str = ""
        self._global_tts_active: bool = False
        self._global_tts_cooldown_active: bool = False
        self._global_tts_sequence: int = 0
        self._global_tts_lease_deadline: float = 0.0
        self._global_tts_hard_deadline: float = 0.0
        self._watchdog_stop: dict | None = None
        self._watchdog_dispatched: bool = False
        self._session_lock = threading.Lock()

    @staticmethod
    def get_instance() -> WakeSessionManager:
        if WakeSessionManager._instance is None:
            with WakeSessionManager._lock:
                if WakeSessionManager._instance is None:
                    WakeSessionManager._instance = WakeSessionManager()
        return WakeSessionManager._instance

    def start_session(self, source: str) -> str:
        with self._session_lock:
            if self._session_id is not None:
                return self._session_id
            sid = str(uuid.uuid4())[:8]
            self._session_id = sid
            self._source = source
            self._state = "online"
            self._detectors_paused = True
            self._started_at = time.time()
            self._last_event_at = time.time()
            self._last_finished_at = 0.0
            self._has_spoken = False
            self._tts_active = False
            self._tts_cooldown_active = False
            self._last_lifecycle_sequence = 0
            self._tts_lease_deadline = 0.0
            self._tts_hard_deadline = 0.0
            self._tts_producer_id = ""
            try:
                from engine.memory.session_memory import clear_session_memory
                clear_session_memory()
            except Exception:
                pass
            try:
                from engine.presence_state import get_presence
                get_presence().update_mode(
                    "online",
                    attention="audio",
                    current_goal="wake detected",
                    last_event="session_started",
                    session_id=sid,
                )
            except Exception:
                pass
            print(f"[SESSION] start id={sid} source={source}", flush=True)
            print(f"[SESSION] detectors_paused=true id={sid}", flush=True)
            return sid

    def is_active(self) -> bool:
        with self._session_lock:
            return self._session_id is not None

    def is_current(self, session_id: str) -> bool:
        with self._session_lock:
            return self._session_id == session_id

    def get_session_id(self) -> str | None:
        with self._session_lock:
            return self._session_id

    def get_session_epoch(self) -> float:
        with self._session_lock:
            return self._started_at if self._session_id is not None else 0.0

    def pause_detectors(self) -> None:
        with self._session_lock:
            self._detectors_paused = True

    def resume_detectors(self) -> None:
        with self._session_lock:
            self._detectors_paused = False
        print(f"[SESSION] detectors_resumed=true", flush=True)

    def are_detectors_paused(self) -> bool:
        with self._session_lock:
            return (
                self._detectors_paused
                or self._global_tts_active
                or self._global_tts_cooldown_active
                or self._watchdog_stop is not None
            )

    def finish_session(self, reason: str = "complete") -> None:
        finished_at = time.time()
        with self._session_lock:
            sid = self._session_id
            self._session_id = None
            self._source = ""
            self._state = "sleep"
            self._detectors_paused = False
            self._started_at = 0.0
            self._last_event_at = 0.0
            self._has_spoken = False
            self._tts_active = False
            self._tts_cooldown_active = False
            self._last_lifecycle_sequence = 0
            self._tts_lease_deadline = 0.0
            self._tts_hard_deadline = 0.0
            self._tts_producer_id = ""
            self._watchdog_stop = None
            self._watchdog_dispatched = False
            if sid and reason not in {"test", "reset"}:
                self._last_finished_at = finished_at
        if sid:
            try:
                from engine.memory.session_memory import clear_session_memory
                clear_session_memory()
            except Exception:
                pass
            try:
                from engine.presence_state import get_presence
                get_presence().update_mode(
                    "sleeping",
                    attention="none",
                    current_goal="waiting for wake word",
                    last_event=f"session_finished:{reason}",
                    session_id="",
                )
            except Exception:
                pass
            try:  # abandon any pending question on sleep so a stale clarification
                from engine.clarification_manager import clear_clarification
                from engine.followup_manager import clear_followup
                clear_clarification(f"sleep:{reason}")
                clear_followup(f"sleep:{reason}")
            except Exception:
                pass
            print(f"[SESSION] finish id={sid} reason={reason}", flush=True)
            print(f"[SLEEP] entering_sleep hotword_rearmed=true reason={reason}", flush=True)
            print(f"[SESSION] detectors_resumed=true", flush=True)

    def ignore_if_stale(self, session_id: str) -> bool:
        with self._session_lock:
            if self._session_id is None:
                return False
            if session_id != self._session_id:
                print(f"[SESSION] stale_event_ignored id={session_id} current={self._session_id}", flush=True)
                return True
            return False

    def set_state(self, state: str) -> None:
        with self._session_lock:
            self._state = state
            self._last_event_at = time.time()

    def get_state(self) -> str:
        with self._session_lock:
            return self._state

    def get_source(self) -> str:
        with self._session_lock:
            return self._source

    def get_idle_seconds(self) -> float:
        with self._session_lock:
            if self._session_id is None:
                return 0.0
            return time.time() - self._last_event_at

    def renew_turn_progress(self, session_id: str) -> bool:
        with self._session_lock:
            if not session_id or session_id != self._session_id or self._tts_active:
                return False
            self._last_event_at = time.time()
            return True

    def apply_tts_lifecycle(
        self,
        session_id: str,
        event_type: str,
        sequence: int,
        producer_id: str = "",
    ) -> bool:
        with self._session_lock:
            if not session_id or self._session_id != session_id:
                return False
            if sequence <= self._last_lifecycle_sequence:
                return False
            if event_type == "tts_started":
                if self._tts_active:
                    return False
                now = time.time()
                self._tts_active = True
                self._tts_cooldown_active = False
                self._has_spoken = True
                self._state = "saying"
                self._tts_lease_deadline = now + _TTS_LEASE_SECONDS
                self._tts_hard_deadline = now + _TTS_HARD_TIMEOUT_SECONDS
                self._tts_producer_id = producer_id
            elif event_type == "tts_heartbeat":
                if not self._tts_active:
                    return False
                if self._tts_producer_id and producer_id != self._tts_producer_id:
                    return False
                if self._watchdog_stop is not None:
                    return False
                now = time.time()
                self._tts_lease_deadline = now + _TTS_LEASE_SECONDS
                self._tts_hard_deadline = now + _TTS_HARD_TIMEOUT_SECONDS
            elif event_type in {"tts_finished", "tts_interrupted"}:
                if not self._tts_active:
                    return False
                if self._tts_producer_id and producer_id != self._tts_producer_id:
                    return False
                self._tts_active = False
                self._tts_cooldown_active = True
                self._has_spoken = True
                self._state = "cooldown"
                self._tts_lease_deadline = 0.0
                self._tts_hard_deadline = 0.0
            elif event_type == "cooldown_complete":
                if self._tts_active or not self._tts_cooldown_active:
                    return False
                if self._tts_producer_id and producer_id != self._tts_producer_id:
                    return False
                self._tts_active = False
                self._tts_cooldown_active = False
                self._state = "cooldown_complete"
                self._tts_lease_deadline = 0.0
                self._tts_hard_deadline = 0.0
                self._tts_producer_id = ""
            else:
                return False
            self._last_lifecycle_sequence = sequence
            self._last_event_at = time.time()
            return True

    def is_tts_active(self) -> bool:
        with self._session_lock:
            return self._tts_active

    def is_tts_cooldown_active(self) -> bool:
        with self._session_lock:
            return self._tts_cooldown_active

    def get_last_lifecycle_sequence(self) -> int:
        with self._session_lock:
            return self._last_lifecycle_sequence

    def apply_global_tts_lifecycle(self, lease_id: str, event_type: str, sequence: int) -> bool:
        with self._session_lock:
            if not lease_id or sequence <= 0:
                return False
            if event_type == "global_tts_started":
                if self._global_tts_active:
                    return False
                now = time.time()
                self._global_tts_lease_id = lease_id
                self._global_tts_active = True
                self._global_tts_sequence = sequence
                self._global_tts_lease_deadline = now + _TTS_LEASE_SECONDS
                self._global_tts_hard_deadline = now + _TTS_HARD_TIMEOUT_SECONDS
                return True
            if lease_id != self._global_tts_lease_id or sequence <= self._global_tts_sequence:
                return False
            if event_type == "global_tts_heartbeat":
                if not self._global_tts_active:
                    return False
                if self._watchdog_stop is not None:
                    return False
                now = time.time()
                self._global_tts_lease_deadline = now + _TTS_LEASE_SECONDS
                self._global_tts_hard_deadline = now + _TTS_HARD_TIMEOUT_SECONDS
            elif event_type in {"global_tts_finished", "global_tts_interrupted"}:
                if not self._global_tts_active:
                    return False
                deadline = time.time() + _AUTO_FINISH_TIMEOUT_SECONDS
                self._global_tts_active = False
                self._global_tts_cooldown_active = True
                self._global_tts_lease_deadline = deadline
                self._global_tts_hard_deadline = deadline
            elif event_type == "global_cooldown_complete":
                if self._global_tts_active or not self._global_tts_cooldown_active:
                    return False
                self._clear_global_tts_locked()
                return True
            else:
                return False
            self._global_tts_sequence = sequence
            return True

    def _clear_global_tts_locked(self) -> None:
        self._global_tts_lease_id = ""
        self._global_tts_active = False
        self._global_tts_cooldown_active = False
        self._global_tts_sequence = 0
        self._global_tts_lease_deadline = 0.0
        self._global_tts_hard_deadline = 0.0

    def reset_transient_state(self) -> None:
        """Clear process-local voice and global TTS leases during startup/tests."""
        with self._session_lock:
            self._session_id = None
            self._source = ""
            self._state = "sleep"
            self._detectors_paused = False
            self._started_at = 0.0
            self._last_event_at = 0.0
            self._last_finished_at = 0.0
            self._has_spoken = False
            self._tts_active = False
            self._tts_cooldown_active = False
            self._last_lifecycle_sequence = 0
            self._tts_lease_deadline = 0.0
            self._tts_hard_deadline = 0.0
            self._tts_producer_id = ""
            self._clear_global_tts_locked()
            self._watchdog_stop = None
            self._watchdog_dispatched = False

    def is_global_tts_active(self) -> bool:
        with self._session_lock:
            return self._global_tts_active or self._global_tts_cooldown_active

    def take_tts_watchdog_request(self) -> dict | None:
        with self._session_lock:
            if self._watchdog_stop is None or self._watchdog_dispatched:
                return None
            self._watchdog_dispatched = True
            return dict(self._watchdog_stop)

    def retry_tts_watchdog_request(self, request_id: str) -> None:
        with self._session_lock:
            if self._watchdog_stop and self._watchdog_stop.get("request_id") == request_id:
                self._watchdog_dispatched = False

    def complete_tts_watchdog(self, request_id: str) -> bool:
        with self._session_lock:
            if not self._watchdog_stop or self._watchdog_stop.get("request_id") != request_id:
                return False
            self._watchdog_stop = None
            self._watchdog_dispatched = False
            return True

    def check_timeout(self) -> bool:
        timeout_reason = ""
        with self._session_lock:
            if self._global_tts_active or self._global_tts_cooldown_active:
                now = time.time()
                deadlines = [
                    value
                    for value in (
                        self._global_tts_lease_deadline,
                        self._global_tts_hard_deadline,
                    )
                    if value > 0.0
                ]
                if deadlines and now >= min(deadlines):
                    if self._watchdog_stop is None:
                        self._watchdog_stop = {
                            "type": "tts_watchdog_stop",
                            "scope": "global",
                            "session_id": "",
                            "session_epoch": 0.0,
                            "lease_id": self._global_tts_lease_id,
                            "producer_id": "",
                            "request_id": uuid.uuid4().hex,
                            "reason": "global_tts_lease_expired",
                        }
                        self._watchdog_dispatched = False
                        print(f"[TTS] global_watchdog_requested lease={self._global_tts_lease_id}", flush=True)
                        return True
                    return False
            if self._session_id is None:
                return False
            if self._tts_active:
                now = time.time()
                deadline = min(
                    value for value in (self._tts_lease_deadline, self._tts_hard_deadline)
                    if value > 0.0
                )
                if now < deadline:
                    return False
                if self._watchdog_stop is None:
                    self._watchdog_stop = {
                        "type": "tts_watchdog_stop",
                        "scope": "voice",
                        "session_id": self._session_id,
                        "session_epoch": self._started_at,
                        "lease_id": "",
                        "producer_id": self._tts_producer_id,
                        "request_id": uuid.uuid4().hex,
                        "reason": "tts_lease_expired",
                    }
                    self._watchdog_dispatched = False
                    self._state = "tts_stop_pending"
                    print(f"[TTS] watchdog_requested id={self._session_id}", flush=True)
                    return True
                return False
            if self._watchdog_stop is not None:
                return False
            idle = time.time() - self._last_event_at
            # Before speech (still thinking): long grace so the session never
            # finishes mid-turn. After a QUESTION: a human answer window. After a
            # plain statement: short re-arm.
            if not self._has_spoken:
                timeout = _PRE_SPEECH_GRACE_SECONDS
            elif _question_is_pending():
                timeout = _AWAITING_ANSWER_TIMEOUT_SECONDS
            else:
                timeout = _AUTO_FINISH_TIMEOUT_SECONDS
            if idle >= timeout:
                sid = self._session_id
                spoke = self._has_spoken
                self._session_id = None
                self._source = ""
                self._state = "sleep"
                self._detectors_paused = False
                self._started_at = 0.0
                self._last_event_at = 0.0
                self._has_spoken = False
                self._tts_active = False
                self._tts_cooldown_active = False
                self._last_lifecycle_sequence = 0
                self._tts_lease_deadline = 0.0
                self._tts_hard_deadline = 0.0
                self._last_finished_at = time.time()
                try:
                    from engine.memory.session_memory import clear_session_memory
                    clear_session_memory()
                except Exception:
                    pass
                try:  # abandon any pending question so it can't resurrect listening
                    from engine.clarification_manager import clear_clarification
                    from engine.followup_manager import clear_followup
                    reason = timeout_reason or "idle_timeout"
                    clear_clarification(f"sleep:{reason}")
                    clear_followup(f"sleep:{reason}")
                except Exception:
                    pass
                reason = timeout_reason or "idle_timeout"
                print(f"[SESSION] auto_timeout_finish id={sid} reason={reason} idle_seconds={idle:.1f} spoke={str(spoke).lower()}", flush=True)
                print(f"[SLEEP] entering_sleep hotword_rearmed=true reason={reason} idle_s={idle:.1f}", flush=True)
                print(f"[SESSION] detectors_resumed=true", flush=True)
                return True
            return False

    def post_session_suppress_remaining_ms(self, now: float | None = None) -> float:
        if _POST_SESSION_WAKE_SUPPRESS_MS <= 0:
            return 0.0
        timestamp = time.time() if now is None else float(now)
        with self._session_lock:
            if self._session_id is not None or self._last_finished_at <= 0:
                return 0.0
            if timestamp + 1.0 < self._last_finished_at:
                # Unit tests often use synthetic clocks; do not mix clock domains.
                return 0.0
            elapsed_ms = (timestamp - self._last_finished_at) * 1000.0
        remaining = _POST_SESSION_WAKE_SUPPRESS_MS - elapsed_ms
        return remaining if remaining > 0 else 0.0

    def is_post_session_suppressed(self, now: float | None = None) -> bool:
        return self.post_session_suppress_remaining_ms(now) > 0


_session_manager = WakeSessionManager.get_instance()


def get_session_manager() -> WakeSessionManager:
    return _session_manager


def start_session(source: str) -> str:
    return _session_manager.start_session(source)


def is_session_active() -> bool:
    return _session_manager.is_active()


def is_current_session(session_id: str) -> bool:
    return _session_manager.is_current(session_id)


def pause_detectors() -> None:
    _session_manager.pause_detectors()


def resume_detectors() -> None:
    _session_manager.resume_detectors()


def are_detectors_paused() -> bool:
    return _session_manager.are_detectors_paused()


def finish_session(reason: str = "complete") -> None:
    _session_manager.finish_session(reason)


def reset_transient_state() -> None:
    _session_manager.reset_transient_state()


def ignore_if_stale(session_id: str) -> bool:
    return _session_manager.ignore_if_stale(session_id)


def session_set_state(state: str) -> None:
    _session_manager.set_state(state)


def session_get_state() -> str:
    return _session_manager.get_state()


def session_get_source() -> str:
    return _session_manager.get_source()


def check_session_timeout() -> bool:
    return _session_manager.check_timeout()


def is_post_session_suppressed(now: float | None = None) -> bool:
    return _session_manager.is_post_session_suppressed(now)
