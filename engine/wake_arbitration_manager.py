from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_sources(key: str, default: str) -> set[str]:
    value = os.getenv(key, default) or default
    return {normalise_source(item) for item in value.split(",") if item.strip()}


def normalise_source(source: str) -> str:
    value = (source or "").strip().lower()
    if value in {"clap", "double-clap", "double clap"}:
        return "double_clap"
    if value in {"ui", "ui_button", "mic_button"}:
        return value
    return value or "unknown"


@dataclass
class WakeCandidate:
    source: str
    detected: bool
    confidence: float
    timestamp: float
    reason: str


@dataclass
class WakeDecision:
    should_wake: bool
    source: str
    confidence: float
    reason: str
    cooldown_active: bool


class WakeArbitrationManager:
    """Single gate for all wake sources.

    Hotword, double clap, and hotkey may all propose candidates. Only this
    manager decides whether a candidate becomes a runtime wake event.
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
        self._allow_sources = set(config.get("allow_sources") or _env_sources("JARVIS_WAKE_ALLOW_SOURCES", "hotword,double_clap,hotkey"))
        self._debug = bool(config.get("debug", _env_bool("JARVIS_WAKE_DEBUG", False)))
        self._last_wake_at = 0.0
        self._last_source = ""
        self._listening = False
        self._last_decision = WakeDecision(False, "", 0.0, "not_evaluated", False)

    def evaluate(self, candidate: WakeCandidate) -> WakeDecision:
        source = normalise_source(candidate.source)
        confidence = max(0.0, min(1.0, float(candidate.confidence or 0.0)))
        timestamp = float(candidate.timestamp or self._clock())

        if self._debug:
            print(
                f"[WAKE_ARB] candidate source={source} confidence={confidence:.4f} "
                f"detected={str(bool(candidate.detected)).lower()} reason={candidate.reason}",
                flush=True,
            )

        if not candidate.detected:
            return self._remember(False, source, confidence, "not_detected", False)
        if source not in self._allow_sources:
            return self._remember(False, source, confidence, "source_not_allowed", False)
        if self._suppress_while_listening and self._listening:
            return self._remember(False, source, confidence, "already_listening", False)

        cooldown_active = False
        if self._last_wake_at > 0 and self._cooldown_ms > 0:
            cooldown_active = (timestamp - self._last_wake_at) * 1000.0 < self._cooldown_ms
        if cooldown_active:
            return self._remember(False, source, confidence, "cooldown", True)

        self._last_wake_at = timestamp
        self._last_source = source
        return self._remember(True, source, confidence, candidate.reason or "detected", False)

    def mark_listening_started(self) -> None:
        self._listening = True

    def mark_listening_done(self) -> None:
        self._listening = False

    def reset(self) -> None:
        self._last_wake_at = 0.0
        self._last_source = ""
        self._listening = False
        self._last_decision = WakeDecision(False, "", 0.0, "reset", False)

    def get_status(self) -> dict:
        return {
            "cooldown_ms": self._cooldown_ms,
            "suppress_while_listening": self._suppress_while_listening,
            "allow_sources": sorted(self._allow_sources),
            "listening": self._listening,
            "last_wake_at": self._last_wake_at,
            "last_source": self._last_source,
            "last_decision": self._last_decision.__dict__.copy(),
        }

    def _remember(self, should_wake: bool, source: str, confidence: float, reason: str, cooldown_active: bool) -> WakeDecision:
        decision = WakeDecision(should_wake, source, confidence, reason, cooldown_active)
        self._last_decision = decision
        if self._debug:
            if should_wake:
                print(f"[WAKE_ARB] decision=wake source={source} confidence={confidence:.4f}", flush=True)
            else:
                print(f"[WAKE_ARB] suppressed reason={reason} source={source}", flush=True)
        return decision
