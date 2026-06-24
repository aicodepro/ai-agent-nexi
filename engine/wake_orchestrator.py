from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_str(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


@dataclass
class WakeSourceResult:
    source: str
    detected: bool
    confidence: float = 0.0
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class WakeDecision:
    should_wake: bool = False
    source: str = ""
    reason: str = "not_evaluated"
    confidence: float = 0.0
    cooldown_active: bool = False


class WakeOrchestrator:
    """Single gate for all wake sources.

    OR logic: hotword OR double_clap OR hotkey.
    Suppresses duplicates during active listening.
    Cooldown after wake.
    Preserves source.
    No cloud call before wake.

    Expected usage:
        chunk = mic.read()
        for detector in [hotword_detector, clap_detector]:
            result = detector.process(chunk)
            decision = orchestrator.evaluate(result)
            if decision.should_wake:
                orchestrator.mark_listening_started()
                start_vad_capture(source=decision.source)
    """

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._clock: Callable[[], float] = config.get("clock", time.time)
        self._cooldown_ms = int(
            config.get(
                "cooldown_ms",
                _env_int("JARVIS_WAKE_COOLDOWN_MS", _env_int("OPENWAKEWORD_COOLDOWN_MS", 1800)),
            )
        )
        self._suppress_while_listening = bool(
            config.get(
                "suppress_while_listening",
                _env_bool("JARVIS_WAKE_SUPPRESS_WHILE_LISTENING", True),
            )
        )
        raw_sources = _env_str("JARVIS_WAKE_SOURCES", "hotword,double_clap,hotkey")
        self._allow_sources = set(config.get("allow_sources")) if config.get("allow_sources") else {s.strip().lower() for s in raw_sources.split(",") if s.strip()}
        self._debug = bool(config.get("debug", _env_bool("JARVIS_WAKE_DEBUG", False)))

        self._last_wake_at = 0.0
        self._last_source = ""
        self._listening = False
        self._last_decision = WakeDecision()

    def evaluate(self, result: WakeSourceResult) -> WakeDecision:
        source = (result.source or "").strip().lower()
        if source in {"clap", "double-clap", "double clap"}:
            source = "double_clap"
        confidence = max(0.0, min(1.0, float(result.confidence or 0.0)))
        timestamp = float(result.timestamp or self._clock())

        if self._debug:
            print(
                f"[WAKE_ORCH] candidate source={source} detected={str(bool(result.detected)).lower()} "
                f"confidence={confidence:.4f}",
                flush=True,
            )

        if not result.detected:
            return self._decide(False, source, confidence, "not_detected")
        if source not in self._allow_sources:
            return self._decide(False, source, confidence, "source_not_allowed")
        if self._suppress_while_listening and self._listening:
            return self._decide(False, source, confidence, "already_listening")

        if self._last_wake_at > 0 and self._cooldown_ms > 0:
            elapsed_ms = (timestamp - self._last_wake_at) * 1000.0
            if elapsed_ms < self._cooldown_ms:
                return self._decide(False, source, confidence, "cooldown", cooldown_active=True)

        self._last_wake_at = timestamp
        self._last_source = source
        return self._decide(True, source, confidence, "detected")

    def mark_listening_started(self) -> None:
        self._listening = True

    def mark_listening_finished(self) -> None:
        self._listening = False

    def reset(self) -> None:
        self._last_wake_at = 0.0
        self._last_source = ""
        self._listening = False
        self._last_decision = WakeDecision()

    def get_status(self) -> dict:
        return {
            "cooldown_ms": self._cooldown_ms,
            "suppress_while_listening": self._suppress_while_listening,
            "allow_sources": sorted(self._allow_sources),
            "listening": self._listening,
            "last_wake_at": self._last_wake_at,
            "last_source": self._last_source,
            "debug": self._debug,
        }

    def _decide(self, should_wake: bool, source: str, confidence: float, reason: str, cooldown_active: bool = False) -> WakeDecision:
        d = WakeDecision(should_wake=should_wake, source=source, reason=reason, confidence=confidence, cooldown_active=cooldown_active)
        self._last_decision = d
        if self._debug:
            if should_wake:
                print(f"[WAKE_ORCH] wake source={source}", flush=True)
            else:
                print(f"[WAKE_ORCH] suppressed reason={reason} source={source}", flush=True)
        return d
