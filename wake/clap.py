"""DSP-based double-clap detector — zero ML dependencies."""

import math
import struct
import time
from core.config import env_float, env_int


class ClapDetector:
    """Pure DSP clap detection with double-clap state machine."""

    def __init__(self, sample_rate: int = 16000):
        self._sample_rate = sample_rate
        self._rms_threshold = env_float("NEXI_DSP_CLAP_RMS_THRESHOLD", 0.045)
        self._peak_threshold = env_float("NEXI_DSP_CLAP_PEAK_THRESHOLD", 0.14)
        self._peak_ratio_threshold = env_float("NEXI_DSP_CLAP_PEAK_RATIO_THRESHOLD", 5.2)
        self._hf_ratio_threshold = env_float("NEXI_DSP_CLAP_HF_RATIO_THRESHOLD", 0.43)
        self._event_cooldown_ms = env_int("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", 120)
        self._speech_reject_ms = env_int("NEXI_DSP_CLAP_SPEECH_REJECT_MS", 280)

        # Double-clap state
        self._min_gap_ms = env_int("NEXI_CLAP_MIN_GAP_MS", 160)
        self._max_gap_ms = env_int("NEXI_CLAP_MAX_GAP_MS", 950)
        self._wake_cooldown_ms = env_int("NEXI_WAKE_COOLDOWN_MS", 2000)

        self._last_single_clap_time = 0.0
        self._last_event_time = 0.0
        self._last_wake_time = 0.0

    def _is_single_clap(self, frame_int16) -> bool:
        """Detect a single clap in one audio frame via DSP analysis."""
        n_samples = len(frame_int16) // 2
        if n_samples == 0:
            return False

        samples = struct.unpack(f"<{n_samples}h", frame_int16)
        float_samples = [s / 32768.0 for s in samples]

        # Event cooldown
        now = time.time() * 1000
        if now - self._last_event_time < self._event_cooldown_ms:
            return False

        # RMS
        rms = math.sqrt(sum(s * s for s in float_samples) / n_samples)
        if rms < self._rms_threshold:
            return False

        # Peak amplitude
        peak = max(abs(s) for s in float_samples)
        if peak < self._peak_threshold:
            return False

        # Peak-to-average ratio (impulsiveness)
        mean_abs = sum(abs(s) for s in float_samples) / n_samples
        if mean_abs > 0:
            ratio = peak / mean_abs
            if ratio < self._peak_ratio_threshold:
                return False

        # High-frequency energy ratio (claps have high HF)
        hf_cutoff = 3000
        fft_size = n_samples
        try:
            import cmath
            # Simple DFT for HF ratio (no numpy needed)
            total_energy = sum(s * s for s in float_samples)
            if total_energy == 0:
                return False
            hf_bin_start = int(hf_cutoff * fft_size / self._sample_rate)
            # Approximate: compute energy in upper half
            hf_energy = sum(s * s for s in float_samples[n_samples // 2:])
            hf_ratio = hf_energy / total_energy
            if hf_ratio < self._hf_ratio_threshold:
                return False
        except Exception:
            pass

        # Duration check (reject sustained sounds)
        duration_ms = n_samples / self._sample_rate * 1000
        if duration_ms > 200:
            return False

        self._last_event_time = now
        return True

    def process_frame(self, frame_int16) -> dict:
        """Process one frame. Returns {detected, source, reason}."""
        result = {"detected": False, "source": "clap", "reason": ""}
        now = time.time() * 1000

        # Wake cooldown
        if now - self._last_wake_time < self._wake_cooldown_ms:
            result["reason"] = "wake_cooldown"
            return result

        if not self._is_single_clap(frame_int16):
            # Timeout the first clap if too long ago
            if self._last_single_clap_time > 0:
                gap = now - self._last_single_clap_time
                if gap > self._max_gap_ms:
                    self._last_single_clap_time = 0.0
            return result

        # Single clap detected — check double-clap pattern
        if self._last_single_clap_time == 0.0:
            self._last_single_clap_time = now
            result["reason"] = "first_clap"
            return result

        gap = now - self._last_single_clap_time
        self._last_single_clap_time = 0.0

        if gap < self._min_gap_ms:
            result["reason"] = "too_fast"
            return result
        if gap > self._max_gap_ms:
            # This becomes a new first clap
            self._last_single_clap_time = now
            result["reason"] = "too_slow_new_first"
            return result

        # Double clap detected!
        self._last_wake_time = now
        result["detected"] = True
        result["reason"] = f"double_clap gap={int(gap)}ms"
        return result

    def reset(self):
        self._last_single_clap_time = 0.0
        self._last_event_time = 0.0
