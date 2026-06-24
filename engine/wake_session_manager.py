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


# How long the wake session may stay idle (detectors paused) before it auto-
# finishes and re-arms the hotword. Was 60s — far too long: the bridge owns the
# turn in a separate process, so this idle timeout is the wake process's only
# re-arm path. Kept short AND speaking-aware (see check_timeout) so the hotword
# returns within a few seconds of speech actually stopping, never mid-response.
_AUTO_FINISH_TIMEOUT_SECONDS = max(1.0, _env_float("NEXI_SESSION_IDLE_TIMEOUT_SECONDS", 3.0))

# Before NEXI has spoken (still thinking / awaiting the bridge's response in the
# other process), allow a longer grace so the session never finishes mid-turn
# and drops the next hotword. Capped so a hung turn can't pause detectors forever.
_PRE_SPEECH_GRACE_SECONDS = max(_AUTO_FINISH_TIMEOUT_SECONDS,
                                _env_float("NEXI_SESSION_PRE_SPEECH_GRACE_SECONDS", 20.0))

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

    def pause_detectors(self) -> None:
        with self._session_lock:
            self._detectors_paused = True

    def resume_detectors(self) -> None:
        with self._session_lock:
            self._detectors_paused = False
        print(f"[SESSION] detectors_resumed=true", flush=True)

    def are_detectors_paused(self) -> bool:
        with self._session_lock:
            return self._detectors_paused

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

    def check_timeout(self) -> bool:
        speaking = False
        try:
            from engine.interrupt_controller import is_speaking
            speaking = bool(is_speaking())
        except Exception:
            speaking = False
        with self._session_lock:
            if self._session_id is None:
                return False
            if speaking:
                # Turn in progress (NEXI is talking): keep the session alive and
                # remember it spoke so we re-arm quickly once speech stops.
                self._has_spoken = True
                self._last_event_at = time.time()
                return False
            idle = time.time() - self._last_event_at
            # After speech: short re-arm. Before speech (still thinking): long
            # grace so the session never finishes mid-turn.
            timeout = _AUTO_FINISH_TIMEOUT_SECONDS if self._has_spoken else _PRE_SPEECH_GRACE_SECONDS
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
                self._last_finished_at = time.time()
                try:
                    from engine.memory.session_memory import clear_session_memory
                    clear_session_memory()
                except Exception:
                    pass
                print(f"[SESSION] auto_timeout_finish id={sid} idle_seconds={idle:.1f} spoke={str(spoke).lower()}", flush=True)
                print(f"[SLEEP] entering_sleep hotword_rearmed=true reason=idle_timeout idle_s={idle:.1f}", flush=True)
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
