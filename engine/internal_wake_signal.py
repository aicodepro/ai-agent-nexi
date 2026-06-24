"""
Internal Wake Signal Bus — replaces keyboard shortcut bridging with
internal Python event signaling for wake and listening state.

Uses the existing runtime_bridge queue when available.
Must not press keys, use OS global shortcuts, or depend on app focus.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


@dataclass
class WakeSignal:
    source: str
    state: str
    phrase: str | None = None
    confidence: float = 0.0
    timestamp: float = 0.0
    reason: str = ""
    text: str | None = None
    session_id: str = ""


class InternalWakeSignalBus:
    """Sends wake/listening/transcript state signals through the
    existing runtime bridge queue or a provided callable.

    No keyboard injection. No global hotkeys. No window focus required.
    """

    def __init__(self, queue: Any = None, post_fn: Callable | None = None, debug: bool | None = None):
        self._queue = queue
        self._post_fn = post_fn
        self._debug = debug if debug is not None else _env_bool("NEXI_INTERNAL_WAKE_SIGNAL_DEBUG", False)
        self._signal_count = 0

    def set_queue(self, queue: Any) -> None:
        self._queue = queue

    @property
    def signal_count(self) -> int:
        return self._signal_count

    def _emit(self, source: str, state: str, *, phrase: str | None = None,
              confidence: float = 0.0, reason: str = "", text: str | None = None,
              session_id: str = "") -> bool:
        self._signal_count += 1
        signal = WakeSignal(source=source, state=state, phrase=phrase,
                            confidence=confidence, timestamp=time.time(),
                            reason=reason, text=text, session_id=session_id)
        if self._debug:
            print(f"[WAKE_SIGNAL] emit source={source} state={state}", flush=True)

        if self._post_fn is not None:
            try:
                self._post_fn(signal)
                return True
            except Exception:
                pass

        if self._queue is not None:
            try:
                from engine.runtime_bridge import post_status
                post_status(self._queue, state, source=source,
                            text=text or phrase or "", session_id=session_id)
                return True
            except Exception:
                pass
        return False

    def emit_wake(self, signal: WakeSignal) -> bool:
        return self._emit(signal.source, "wake_detected",
                          phrase=signal.phrase, confidence=signal.confidence,
                          reason=signal.reason, session_id=signal.session_id)

    def emit_listening_started(self, source: str, session_id: str = "") -> bool:
        return self._emit(source, "listening", session_id=session_id)

    def emit_waiting_for_speech(self, source: str, session_id: str = "") -> bool:
        return self._emit(source, "waiting_for_speech", session_id=session_id)

    def emit_recognising(self, source: str, session_id: str = "") -> bool:
        return self._emit(source, "recognising", session_id=session_id)

    def emit_transcript(self, text: str, source: str, session_id: str = "") -> bool:
        return self._emit(source, "asr_result", text=text, session_id=session_id)

    def emit_assistant_response(self, text: str) -> bool:
        return self._emit("assistant", "assistant_response", text=text)

    def emit_tts_started(self) -> bool:
        return self._emit("assistant", "saying")

    def emit_tts_done(self) -> bool:
        return self._emit("assistant", "sleep")

    def emit_no_speech(self, source: str) -> bool:
        return self._emit(source, "no_speech")
