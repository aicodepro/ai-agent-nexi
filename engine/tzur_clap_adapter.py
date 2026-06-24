"""Tzur-style clap detection adapter for JARVIS.

Adapted from TzurSoffer/clapDetection (MIT License):
  GitHub: https://github.com/TzurSoffer/clapDetection

Algorithm:
  1. Bandpass filter (5th-order Butterworth, 100-4000 Hz) to isolate clap frequencies
  2. Dynamic threshold via EMA on max filtered amplitude
  3. Peak detection (scipy.signal.find_peaks) above EMA + bias
  4. Debounce gate (150 ms) to avoid double-fires
  5. Pattern extraction: claps within 80 ms grouped as double/triple
  6. Pattern reset after 350 ms of silence

Accepts raw int16 PCM bytes (same format as Jarvis audio_pipeline).
Does NOT open its own microphone stream.
"""

from __future__ import annotations

import math
import struct
import time
from collections import deque
from typing import Optional

import numpy as np
from scipy.signal import butter, lfilter, find_peaks


SAMPLE_RATE = 16000
BUFFER_SIZE = 1280


class TzurClapAdapter:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        *,
        lowcut: float = 100.0,
        highcut: float = 4000.0,
        threshold_bias: float = 0.08,
        ema_alpha: float = 0.9,
        ema_dampen: float = 0.5,
        debounce_ms: float = 150.0,
        clap_interval_ms: float = 700.0,
        min_clap_gap_ms: float = 180.0,
        max_clap_gap_ms: float = 900.0,
        pattern_reset_ms: float = 1200.0,
        min_amplitude: float = 0.06,
        clock: Optional[callable] = None,
    ):
        self._clock = clock or time.time
        self._rate = max(4000, int(sample_rate))

        self._lowcut = float(lowcut)
        self._highcut = float(highcut)
        self._threshold_bias = float(threshold_bias)
        self._ema_alpha = float(ema_alpha)
        self._ema_dampen = float(ema_dampen)
        self._debounce_sec = debounce_ms / 1000.0
        self._clap_interval_sec = clap_interval_ms / 1000.0
        self._min_clap_gap_sec = min_clap_gap_ms / 1000.0
        self._max_clap_gap_sec = max_clap_gap_ms / 1000.0
        self._pattern_reset_sec = pattern_reset_ms / 1000.0
        self._min_amplitude = float(min_amplitude)

        self._ema_threshold: float = 0.01
        self._clap_times: list[float] = []
        self._last_clap_at: float = 0.0
        self._last_cooldown_at: float = 0.0
        self._cooldown_sec: float = 0.0
        self._ready: bool = False
        self._total_chunks: int = 0
        self._detected_single: int = 0
        self._detected_double: int = 0

        self._last_amplitude: float = 0.0
        self._last_filtered_max: float = 0.0
        self._last_gap_ms: float | None = None
        self._recent_amplitudes: deque[float] = deque(maxlen=50)

        try:
            nyquist = self._rate / 2.0
            low = max(10.0, min(self._lowcut, nyquist - 1))
            high = max(low + 10.0, min(self._highcut, nyquist - 1))
            b, a = butter(5, [low / nyquist, high / nyquist], btype="band")
            self._b = b
            self._a = a
            self._ready = True
        except Exception as e:
            print(f"[CLAP_TZUR] filter_init_failed reason={type(e).__name__}", flush=True)
            self._b = None
            self._a = None
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def ema_threshold(self) -> float:
        return self._ema_threshold

    @property
    def last_amplitude(self) -> float:
        return self._last_amplitude

    @property
    def last_filtered_max(self) -> float:
        return self._last_filtered_max

    def get_debug_snapshot(self) -> dict:
        return {
            "ready": self._ready,
            "ema_threshold": round(self._ema_threshold, 6),
            "last_amplitude": round(self._last_amplitude, 6),
            "last_filtered_max": round(self._last_filtered_max, 6),
            "last_gap_ms": None if self._last_gap_ms is None else round(self._last_gap_ms, 1),
            "total_chunks": self._total_chunks,
            "detected_single": self._detected_single,
            "detected_double": self._detected_double,
            "clap_times": len(self._clap_times),
            "rate": self._rate,
            "min_amplitude": self._min_amplitude,
            "min_gap_ms": round(self._min_clap_gap_sec * 1000.0, 1),
            "max_gap_ms": round(self._max_clap_gap_sec * 1000.0, 1),
        }

    def set_cooldown(self, seconds: float) -> None:
        self._cooldown_sec = max(0.0, float(seconds))
        if seconds > 0:
            self._last_cooldown_at = self._clock()

    def reset(self) -> None:
        self._clap_times = []
        self._ema_threshold = 0.01
        self._last_amplitude = 0.0
        self._last_filtered_max = 0.0
        self._last_gap_ms = None

    def process_audio_chunk(self, frame_int16: bytes) -> dict:
        """Process a raw int16 PCM chunk through the Tzur detector.

        Returns a dict:
            clap: bool        — single clap detected this frame
            wake: bool         — double clap pattern detected
            source: str|None   — "clap" if wake
            amplitude: float   — max amplitude this chunk
            filtered_max: float — max after bandpass
            threshold: float   — current EMA threshold
            backend: str       — "tzur"
        """
        if not self._ready or not frame_int16:
            return self._no_clap("not_ready")

        now = self._clock()

        if self._cooldown_sec > 0 and (now - self._last_cooldown_at) < self._cooldown_sec:
            return {"clap": False, "wake": False, "source": None,
                    "amplitude": 0.0, "filtered_max": 0.0,
                    "threshold": self._ema_threshold, "backend": "tzur",
                    "cooldown": True}

        try:
            n = len(frame_int16) // 2
            if n < 4:
                return self._no_clap("too_short")
            samples = np.array(struct.unpack(f"<{n}h", frame_int16), dtype=np.float32)
        except Exception:
            return self._no_clap("unpack_error")

        amplitude = float(np.max(np.abs(samples))) / 32768.0
        self._last_amplitude = amplitude
        self._total_chunks += 1

        if amplitude < self._min_amplitude:
            self._update_noise(amplitude)
            return self._no_clap("below_min", amplitude=amplitude)

        try:
            filtered = lfilter(self._b, self._a, samples)
        except Exception:
            return self._no_clap("filter_error", amplitude=amplitude)

        filtered_abs = np.abs(filtered)
        filtered_max = float(np.max(filtered_abs)) / 32768.0
        self._last_filtered_max = filtered_max

        self._ema_threshold = (
            self._ema_alpha * self._ema_threshold
            + (1.0 - self._ema_alpha) * filtered_max * self._ema_dampen
        )

        effective_threshold = self._ema_threshold + self._threshold_bias

        try:
            peaks, props = find_peaks(filtered_abs, height=effective_threshold * 32768.0)
        except Exception:
            return self._no_clap("peak_error", amplitude=amplitude, filtered_max=filtered_max)

        if len(peaks) == 0:
            self._update_noise(amplitude)
            return self._no_clap("no_peaks", amplitude=amplitude,
                                 filtered_max=filtered_max)

        if now - self._last_clap_at < self._debounce_sec:
            return self._no_clap("debounce", amplitude=amplitude,
                                 filtered_max=filtered_max)

        self._last_clap_at = now
        self._clap_times.append(now)

        pattern = self._extract_pattern(now)
        is_double, gap_ms = self._double_clap_gap(now)
        self._last_gap_ms = gap_ms
        if is_double:
            self._detected_double += 1
            self._clap_times = []
            return {"clap": True, "wake": True, "source": "double_clap",
                    "amplitude": amplitude, "filtered_max": filtered_max,
                    "threshold": self._ema_threshold, "backend": "tzur",
                    "cooldown": False, "gap_ms": gap_ms,
                    "pattern": pattern, "reason": "double_clap"}

        self._detected_single += 1
        return {"clap": True, "wake": False, "source": None,
                "amplitude": amplitude, "filtered_max": filtered_max,
                "threshold": self._ema_threshold, "backend": "tzur",
                "cooldown": False, "gap_ms": gap_ms,
                "pattern": pattern, "reason": "single_clap"}

    def _no_clap(self, reason: str = "", *, amplitude: float = 0.0,
                 filtered_max: float = 0.0) -> dict:
        return {"clap": False, "wake": False, "source": None,
                "amplitude": amplitude, "filtered_max": filtered_max,
                "threshold": self._ema_threshold, "backend": "tzur",
                "cooldown": False, "reason": reason, "gap_ms": None,
                "pattern": []}

    def _update_noise(self, amplitude: float) -> None:
        self._recent_amplitudes.append(amplitude)

    def _extract_pattern(self, now: float) -> list[int]:
        """Group recent claps into a pattern. Claps within clap_interval
        are part of a multi-clap group (2=double, 3=triple)."""
        recent = [t for t in self._clap_times if now - t <= self._pattern_reset_sec]
        if len(recent) < 2:
            return [1] if recent else []

        intervals = [(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        pattern = []
        group_size = 1
        for gap in intervals:
            if gap <= self._clap_interval_sec:
                group_size += 1
            else:
                pattern.append(group_size)
                group_size = 1
        pattern.append(group_size)
        return pattern

    def _count_recent_claps(self, now: float, window: float = None) -> int:
        if window is None:
            window = self._clap_interval_sec * 1.5
        recent = [t for t in self._clap_times if now - t <= window]
        return len(recent)

    def _double_clap_gap(self, now: float) -> tuple[bool, float | None]:
        """Return whether two distinct claps are in the valid gap window."""
        times = [t for t in self._clap_times if now - t <= self._max_clap_gap_sec]
        if len(times) < 2:
            return False, None
        # Check each adjacent pair
        for i in range(len(times) - 1):
            gap = times[i + 1] - times[i]
            if self._min_clap_gap_sec <= gap <= self._max_clap_gap_sec:
                return True, gap * 1000.0
        if len(times) >= 2:
            return False, (times[-1] - times[-2]) * 1000.0
        return False, None


def create_tzur_adapter(sample_rate: int = SAMPLE_RATE, **kwargs) -> TzurClapAdapter:
    return TzurClapAdapter(sample_rate=sample_rate, **kwargs)
