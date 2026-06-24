from __future__ import annotations
import os
import threading
import time
from dataclasses import dataclass

def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default

@dataclass
class BargeInResult:
    interrupted: bool
    reason: str = ""
    level: str = "none"

    @property
    def interruption_reason(self) -> str:
        """Alias for `reason` (name expected by some callers/tests)."""
        return self.reason


def get_session_manager():
    """Lazy accessor for the wake session manager (kept patchable at module level)."""
    from engine.wake_session_manager import get_session_manager as _gsm
    return _gsm()


def _is_speaking() -> bool:
    """Module-level speaking predicate (patchable; used by interrupt())."""
    return _manager.is_speaking()


class BargeInManager:
    """Small coordinator for interrupting active speech before new capture."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_interrupt_at = 0.0

    @property
    def enabled(self) -> bool:
        return _env_bool("BARGE_IN_ENABLED", True)

    @property
    def min_speech_ms(self) -> int:
        return max(0, _env_int("BARGE_IN_MIN_SPEECH_MS", 200))

    @property
    def cancel_ms(self) -> int:
        return max(self.min_speech_ms, _env_int("BARGE_IN_CANCEL_MS", 1500))

    @property
    def debounce_ms(self) -> int:
        return max(0, _env_int("BARGE_IN_DEBOUNCE_MS", 500))

    def is_speaking(self) -> bool:
        try:
            from engine.interrupt_controller import is_speaking
            return bool(is_speaking())
        except Exception:
            return False

    def set_speaking_state(self, value: bool) -> None:
        try:
            from engine.interrupt_controller import set_speaking
            set_speaking(bool(value))
        except Exception:
            pass

    def interrupt(self, *, source: str = "barge_in", reason: str = "wake_detected", speech_ms: int | None = None) -> BargeInResult:
        if not self.enabled:
            return BargeInResult(False, "disabled")
        if speech_ms is not None and speech_ms < self.min_speech_ms:
            return BargeInResult(False, "speech_too_short")
        if not _is_speaking():
            return BargeInResult(False, "not_speaking")

        now = time.time()
        with self._lock:
            elapsed_ms = (now - self._last_interrupt_at) * 1000.0
            if self._last_interrupt_at and elapsed_ms < self.debounce_ms:
                return BargeInResult(False, "debounced")
            self._last_interrupt_at = now

        level = "cancel" if speech_ms is None or speech_ms >= self.cancel_ms else "pause"
        safe_source = (source or "barge_in").strip() or "barge_in"
        safe_reason = (reason or "wake_detected").strip() or "wake_detected"
        try:
            from engine.interrupt_controller import request_interrupt
            request_interrupt(safe_source, safe_reason)
        except Exception:
            pass
        try:
            from engine.turn_manager import request_interrupt as request_turn_interrupt
            request_turn_interrupt(safe_source, safe_reason)
        except Exception:
            pass
        try:
            from engine import groq_tts
            groq_tts.stop()
        except Exception:
            pass
        print(f"[BARGE_IN] interrupted=true source={safe_source} level={level} reason={safe_reason}", flush=True)
        return BargeInResult(True, safe_reason, level)

    def reset(self) -> None:
        with self._lock:
            self._last_interrupt_at = 0.0


_manager = BargeInManager()


def get_barge_in_manager() -> BargeInManager:
    return _manager


def is_speaking() -> bool:
    return _manager.is_speaking()


def is_barge_in_active() -> bool:
    return _manager.is_speaking()


def set_speaking_state(value: bool) -> None:
    _manager.set_speaking_state(value)


def interrupt(*, source: str = "barge_in", reason: str = "wake_detected", speech_ms: int | None = None) -> BargeInResult:
    return _manager.interrupt(source=source, reason=reason, speech_ms=speech_ms)


def reset_barge_in_state() -> None:
    _manager.reset()
