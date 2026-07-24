"""Lightweight DSP-based clap event detector.

No ML dependencies.
Detects acoustic clap events using:
  - RMS amplitude threshold (rejects silence)
  - Peak amplitude threshold (absolute peak, rejects low transients)
  - RMS peak-to-average ratio (transient spike vs sustained)
  - High-frequency energy ratio (clap has broad spectrum)
  - Short duration window (rejects sustained speech/noise)
  - Speech rejection via sustained-energy check
  - Cooldown/debounce to prevent double-fire on one acoustic event

Config env vars:
  NEXI_DSP_CLAP_ENABLED=true
  NEXI_DSP_CLAP_RMS_THRESHOLD=0.030      min RMS for a clap frame
  NEXI_DSP_CLAP_PEAK_THRESHOLD=0.10      min absolute peak (normalized)
  NEXI_DSP_CLAP_PEAK_RATIO=4.0           peak / avg RMS ratio
  NEXI_DSP_CLAP_HF_RATIO=0.30            min high-freq energy ratio
  NEXI_DSP_CLAP_EVENT_COOLDOWN_MS=80     cooldown between individual clap events
  NEXI_DSP_CLAP_SPEECH_REJECT_MS=250     reject sustained energy lasting longer than this
  NEXI_DSP_CLAP_DEBUG=false
"""

from __future__ import annotations

import math
import os
import struct
import time
from dataclasses import dataclass
from typing import Callable


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_float_aliases(keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        value = os.getenv(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _env_int_aliases(keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        value = os.getenv(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


@dataclass
class DspClapResult:
    is_clap: bool
    confidence: float
    timestamp: float
    rms: float
    peak_ratio: float
    hf_ratio: float
    duration_ms: float
    reason: str


class DspClapBackend:
    """Real-time DSP clap detector operating on PCM16 frames."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        clock: Callable[[], float] | None = None,
    ):
        self._sample_rate = sample_rate
        self._clock = clock or time.time
        self._debug = _env_bool("NEXI_DSP_CLAP_DEBUG", False)

        self._rms_threshold = _env_float_aliases(
            ("NEXI_DSP_CLAP_RMS_THRESHOLD", "JARVIS_DSP_CLAP_RMS_THRESHOLD"), 0.030
        )
        self._peak_threshold = _env_float_aliases(
            ("NEXI_DSP_CLAP_PEAK_THRESHOLD", "JARVIS_DSP_CLAP_PEAK_THRESHOLD"), 0.10
        )
        self._peak_ratio_threshold = _env_float_aliases((
            "NEXI_DSP_CLAP_PEAK_RATIO",
            "NEXI_DSP_CLAP_PEAK_RATIO_THRESHOLD",
            "JARVIS_DSP_CLAP_PEAK_RATIO",
            "JARVIS_DSP_CLAP_PEAK_RATIO_THRESHOLD",
        ), 4.0)
        self._hf_ratio_threshold = _env_float_aliases((
            "NEXI_DSP_CLAP_HF_RATIO",
            "NEXI_DSP_CLAP_HF_RATIO_THRESHOLD",
            "JARVIS_DSP_CLAP_HF_RATIO",
            "JARVIS_DSP_CLAP_HF_RATIO_THRESHOLD",
        ), 0.30)
        self._event_cooldown_ms = _env_int_aliases(
            ("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "JARVIS_DSP_CLAP_EVENT_COOLDOWN_MS"), 80
        )
        self._speech_reject_ms = _env_int_aliases(
            ("NEXI_DSP_CLAP_SPEECH_REJECT_MS", "JARVIS_DSP_CLAP_SPEECH_REJECT_MS"), 250
        )

        self._last_event_time = 0.0
        self._speech_start_time: float | None = None
        self._stats: dict = {}
        self._event_counter = 0
        self._last_result = DspClapResult(
            is_clap=False, confidence=0.0, timestamp=0.0,
            rms=0.0, peak_ratio=0.0, hf_ratio=0.0,
            duration_ms=0.0, reason="init",
        )

    def process_pcm16(self, pcm16: bytes, timestamp: float | None = None) -> DspClapResult:
        now = timestamp if timestamp is not None else self._clock()

        if not pcm16 or len(pcm16) < 64:
            return self._make_result(False, 0.0, now, 0.0, 0.0, 0.0, 0.0, "too_short")

        n = len(pcm16) // 2
        if n <= 0:
            return self._make_result(False, 0.0, now, 0.0, 0.0, 0.0, 0.0, "empty")

        samples = struct.unpack(f"<{n}h", pcm16)

        sum_sq = 0
        peak = 0
        hf_energy = 0.0
        total_energy = 0.0
        previous = samples[0]
        for i, s in enumerate(samples):
            sq = s * s
            sum_sq += sq
            abs_s = abs(s)
            if abs_s > peak:
                peak = abs_s
            if i > 0:
                delta = s - previous
                hf_energy += delta * delta
            previous = s
            total_energy += sq

        rms = (sum_sq / n) ** 0.5 / 32768.0
        peak_norm = peak / 32768.0
        avg = rms
        peak_ratio = peak_norm / avg if avg > 1e-10 else 0.0
        hf_ratio = min(1.0, hf_energy / (4.0 * total_energy)) if total_energy > 0 else 0.0
        duration_ms = (n / self._sample_rate) * 1000.0

        is_clap = False
        confidence = 0.0
        reason = "none"

        # Log candidate features before decision
        if self._debug:
            candidate_r = self._make_result(False, 0.0, now, rms, peak_ratio, hf_ratio, duration_ms, "candidate")
            print(
                f"[DSP_CLAP] candidate rms={rms:.4f} peak={peak_norm:.4f} "
                f"peak_ratio={peak_ratio:.2f} hf_ratio={hf_ratio:.2f} "
                f"duration_ms={duration_ms:.0f}",
                flush=True,
            )

        # Check cooldown
        since_last = (now - self._last_event_time) * 1000.0
        if since_last < self._event_cooldown_ms:
            reason = f"cooldown_{since_last:.0f}ms"
        elif duration_ms > 200:
            reason = f"too_long_{duration_ms:.0f}ms"
        elif rms < self._rms_threshold:
            reason = f"low_rms_{rms:.4f}"
        elif peak_norm < self._peak_threshold:
            reason = f"low_peak_{peak_norm:.4f}"
        elif peak_ratio < self._peak_ratio_threshold:
            reason = f"low_ratio_{peak_ratio:.2f}"
        elif hf_ratio < self._hf_ratio_threshold:
            reason = f"low_hf_{hf_ratio:.2f}"
        else:
            # All threshold checks passed — this is a transient event.
            # First, rule out sustained speech:
            if rms > self._rms_threshold * 0.5 and peak_ratio < self._peak_ratio_threshold * 0.8:
                if self._speech_start_time is None:
                    self._speech_start_time = now
                speech_dur = (now - self._speech_start_time) * 1000.0
                if speech_dur > self._speech_reject_ms:
                    reason = f"sustained_speech_like_{speech_dur:.0f}ms"
                else:
                    reason = f"tracking_speech_{speech_dur:.0f}ms"
            else:
                # Not sustained speech. All thresholds met → genuine clap.
                self._speech_start_time = None
                self._event_counter += 1
                is_clap = True
                confidence = min(1.0, (rms / self._rms_threshold) * 0.3 +
                                (peak_ratio / self._peak_ratio_threshold) * 0.3 +
                                (hf_ratio / self._hf_ratio_threshold) * 0.2 +
                                (peak_norm / self._peak_threshold) * 0.2)
                reason = f"clap_detected_id={self._event_counter}"
                self._last_event_time = now

        self._last_result = self._make_result(
            is_clap, confidence, now, rms, peak_ratio, hf_ratio, duration_ms, reason
        )

        if self._debug:
            status = "accepted" if is_clap else "rejected"
            reject = reason if not is_clap else ""
            print(
                f"[DSP_CLAP] {status} rms={rms:.4f} peak={peak_norm:.4f} "
                f"peak_ratio={peak_ratio:.2f} hf_ratio={hf_ratio:.2f} "
                f"dur={duration_ms:.0f}ms reason={reason}",
                flush=True,
            )

        return self._last_result

    def _make_result(
        self, is_clap, confidence, ts, rms, pr, hfr, dur, reason
    ) -> DspClapResult:
        return DspClapResult(
            is_clap=is_clap,
            confidence=confidence,
            timestamp=ts,
            rms=rms,
            peak_ratio=pr,
            hf_ratio=hfr,
            duration_ms=dur,
            reason=reason,
        )

    def reset(self) -> None:
        self._last_event_time = 0.0
        self._speech_start_time = None
        self._last_result = DspClapResult(
            is_clap=False, confidence=0.0, timestamp=0.0,
            rms=0.0, peak_ratio=0.0, hf_ratio=0.0,
            duration_ms=0.0, reason="reset",
        )

    def get_debug_snapshot(self) -> dict:
        return {
            "rms_threshold": self._rms_threshold,
            "peak_threshold": self._peak_threshold,
            "peak_ratio_threshold": self._peak_ratio_threshold,
            "hf_ratio_threshold": self._hf_ratio_threshold,
            "event_cooldown_ms": self._event_cooldown_ms,
            "speech_reject_ms": self._speech_reject_ms,
            "last_result": {
                "is_clap": self._last_result.is_clap,
                "confidence": self._last_result.confidence,
                "rms": self._last_result.rms,
                "peak_ratio": self._last_result.peak_ratio,
                "hf_ratio": self._last_result.hf_ratio,
                "duration_ms": self._last_result.duration_ms,
                "reason": self._last_result.reason,
            },
        }

    def get_status(self) -> dict:
        return {
            "enabled": True,
            "backend": "dsp_clap",
            "sample_rate": self._sample_rate,
            "rms_threshold": self._rms_threshold,
            "peak_threshold": self._peak_threshold,
            "peak_ratio_threshold": self._peak_ratio_threshold,
            "hf_ratio_threshold": self._hf_ratio_threshold,
        }


class DoubleClapDetector:
    """Backend-agnostic double-clap state machine.

    States:
        stage_first_clap — first clap stored, waiting for second
        first_clap_waiting — alias for stage_first_clap
        stage_two_clap — second clap received within valid window
        double_clap — wake=true
        cooldown — post-wake cooldown
        reset — idle

    Usage:
        detector = DoubleClapDetector(clock=time.time)
        result = detector.detect(clap_timestamp_seconds)
        if result["wake"]: trigger_wake()
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        min_gap_ms: int = 100,
        max_gap_ms: int = 4500,
        cooldown_ms: int = 1500,
    ):
        self._clock = clock or time.time
        self._min_gap_ms = max(1, int(min_gap_ms))
        self._max_gap_ms = max(self._min_gap_ms + 1, int(max_gap_ms))
        self._cooldown_ms = max(0, int(cooldown_ms))
        self._state = "reset"
        self._first_clap_time = 0.0
        self._last_wake_at = 0.0
        self._debug = _env_bool("NEXI_CLAP_DEBUG", False) or _env_bool("DOUBLE_CLAP_DEBUG", False)

    def detect(self, clap_timestamp: float | None = None) -> dict:
        now = clap_timestamp if clap_timestamp is not None else self._clock()

        if self._last_wake_at > 0:
            since_wake = (now - self._last_wake_at) * 1000.0
            if since_wake < self._cooldown_ms:
                return {"wake": False, "clap": False, "state": "cooldown", "gap_ms": None, "reason": "cooldown"}

        if self._state in ("reset", "double_clap", "cooldown"):
            self._state = "stage_first_clap"
            self._first_clap_time = now
            if self._debug:
                print(f"[DOUBLE_CLAP] first_clap stored wake=false", flush=True)
            return {"wake": False, "clap": True, "state": "stage_first_clap", "gap_ms": None, "reason": "first_clap_waiting"}

        gap = (now - self._first_clap_time) * 1000.0

        if gap < self._min_gap_ms:
            if self._debug:
                print(f"[DOUBLE_CLAP] too_soon gap_ms={gap:.0f} ignore", flush=True)
            return {"wake": False, "clap": False, "state": self._state, "gap_ms": gap, "reason": "too_soon"}

        if gap <= self._max_gap_ms:
            self._state = "double_clap"
            self._last_wake_at = now
            self._first_clap_time = 0.0
            if self._debug:
                print(f"[DOUBLE_CLAP] detected gap_ms={gap:.0f} wake=true", flush=True)
            return {"wake": True, "clap": True, "state": "double_clap", "gap_ms": gap, "reason": "double_clap"}

        self._state = "reset"
        self._first_clap_time = 0.0
        if self._debug:
            print(f"[DOUBLE_CLAP] too_late gap_ms={gap:.0f} reset", flush=True)
        return {"wake": False, "clap": True, "state": "reset", "gap_ms": gap, "reason": "too_late"}

    def check_timeout(self, now: float | None = None) -> dict | None:
        now = now if now is not None else self._clock()
        if self._state not in ("stage_first_clap", "first_clap_waiting"):
            return None
        gap = (now - self._first_clap_time) * 1000.0
        if gap > self._max_gap_ms:
            self._state = "reset"
            self._first_clap_time = 0.0
            if self._debug:
                print(f"[DOUBLE_CLAP] timeout gap_ms={gap:.0f} reset", flush=True)
            return {"state": "reset", "reason": "too_late_timeout", "gap_ms": gap}
        return None

    def get_status(self) -> dict:
        return {
            "state": self._state,
            "first_clap_time": self._first_clap_time,
            "last_wake_at": self._last_wake_at,
            "min_gap_ms": self._min_gap_ms,
            "max_gap_ms": self._max_gap_ms,
            "cooldown_ms": self._cooldown_ms,
        }

    def reset(self) -> None:
        self._state = "reset"
        self._first_clap_time = 0.0
        self._last_wake_at = 0.0
