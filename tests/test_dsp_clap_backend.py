"""Tests for DSP clap backend — fast no-dependency clap detector."""

import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_impulse(duration_samples: int = 800, peak_val: int = 20000) -> bytes:
    """Create a short high-amplitude impulse (clap-like)."""
    samples = [0] * duration_samples
    for i in range(20):
        idx = duration_samples // 2 + i
        if idx < duration_samples:
            samples[idx] = peak_val
            if idx + 1 < duration_samples:
                samples[idx + 1] = -peak_val // 2
    return struct.pack(f"<{len(samples)}h", *samples)


def _make_silence(duration_samples: int = 1600) -> bytes:
    return b"\x00\x00" * duration_samples


class TestDspClapBackend:
    def test_creates_with_defaults(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        status = dsp.get_status()
        assert status["backend"] == "dsp_clap"
        assert status["enabled"] is True
        assert status["sample_rate"] == 16000

    def test_silence_rejected(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_silence())
        assert r.is_clap is False
        assert "low_rms" in r.reason

    def test_short_frame_rejected(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(b"\x00\x00" * 16)
        assert r.is_clap is False
        assert "too_short" in r.reason

    def test_clap_impulse_detected(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_impulse(800))
        assert r.is_clap is True
        assert r.confidence > 0.5
        assert r.peak_ratio > 3.0
        assert "clap_detected" in r.reason

    def test_too_long_rejected(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_impulse(6400))  # 400ms at 16kHz
        assert r.is_clap is False
        assert "too_long" in r.reason

    def test_low_amplitude_not_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_impulse(800, peak_val=2000))
        assert r.is_clap is False
        assert "low_rms" in r.reason or "low_peak_ratio" in r.reason

    def test_reset_clears_event_cooldown(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r1 = dsp.process_pcm16(_make_impulse(800))
        assert r1.is_clap is True
        dsp.reset()
        r2 = dsp.process_pcm16(_make_impulse(800))
        assert r2.is_clap is True

    def test_debug_snapshot_contains_stats(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        dsp.process_pcm16(_make_impulse(800))
        snap = dsp.get_debug_snapshot()
        assert "last_result" in snap
        assert snap["last_result"]["is_clap"] is True

    def test_sustained_noise_not_clap_because_low_peak_ratio(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        samples = [5000] * 1600  # sustained noise, no transient peak
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False
