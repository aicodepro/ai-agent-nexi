"""Tests for DSP clap backend — fast no-dependency clap detector."""

import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _stable_dsp_thresholds(monkeypatch):
    monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.030")
    monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.10")
    monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "4.0")
    monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.30")


def _make_impulse(duration_samples: int = 800, peak_val: int = 20000) -> bytes:
    """Create a short high-amplitude impulse (clap-like)."""
    samples = [0] * duration_samples
    for i in range(20):
        idx = duration_samples // 2 + i
        if idx < duration_samples:
            samples[idx] = peak_val if i % 2 == 0 else -peak_val // 2
    return struct.pack(f"<{len(samples)}h", *samples)


def _make_silence(duration_samples: int = 1600) -> bytes:
    return b"\x00\x00" * duration_samples


def _make_broadband_impulse(start: int, duration_samples: int = 800) -> bytes:
    samples = [0] * duration_samples
    for offset in range(24):
        samples[start + offset] = 20000 if offset % 2 == 0 else -14000
    return struct.pack(f"<{len(samples)}h", *samples)


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

    def test_high_frequency_ratio_is_independent_of_impulse_position(self):
        from engine.dsp_clap_backend import DspClapBackend

        early = DspClapBackend().process_pcm16(_make_broadband_impulse(100), timestamp=10.0)
        late = DspClapBackend().process_pcm16(_make_broadband_impulse(650), timestamp=10.0)

        assert early.is_clap is True
        assert late.is_clap is True
        assert early.hf_ratio == pytest.approx(late.hf_ratio, abs=0.01)

    def test_threshold_suffix_and_legacy_env_aliases(self, monkeypatch):
        from engine.dsp_clap_backend import DspClapBackend

        for key in ("NEXI_DSP_CLAP_PEAK_RATIO", "NEXI_DSP_CLAP_HF_RATIO"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO_THRESHOLD", "5.7")
        monkeypatch.setenv("JARVIS_DSP_CLAP_HF_RATIO_THRESHOLD", "0.47")

        dsp = DspClapBackend()

        assert dsp.get_status()["peak_ratio_threshold"] == 5.7
        assert dsp.get_status()["hf_ratio_threshold"] == 0.47
