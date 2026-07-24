"""Tests: DSP balanced thresholds detect clap events correctly."""

import math
import os
import struct
import sys
import time as time_module

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def make_clap_signal(peak_val: float = 0.5, n_impulse: int = 200, total: int = 1280):
    """HF-rich impulse. Signal placed at index >= 960 so hf_freq >= 3000Hz."""
    samples = [0] * total
    start = total * 3 // 4
    for i in range(n_impulse):
        frac = 1.0 - (i / n_impulse)
        idx = start + i
        if idx >= total:
            break
        t = i / 16000.0
        val = (math.sin(2 * math.pi * 3500 * t) * 0.4 +
               math.sin(2 * math.pi * 5000 * t) * 0.4 +
               math.sin(2 * math.pi * 7000 * t) * 0.4)
        val *= frac * peak_val
        samples[idx] = int(val * 32767)
    return struct.pack(f"<{len(samples)}h", *samples)


SILENCE_80 = b"\x00\x00" * 1280


def make_continuous_noise(amp: float = 0.03):
    import random
    rng = random.Random(99)
    n = 1280
    samples = [int(amp * 32767 * (rng.random() - 0.5)) for _ in range(n)]
    return struct.pack(f"<{len(samples)}h", *samples)


class TickClock:
    """Clock that advances by step_seconds per call."""
    def __init__(self, start: float = 1000.0, step: float = 0.08):
        self._t = start
        self._step = step
    def __call__(self):
        v = self._t
        self._t += self._step
        return v


class TestDspDoubleClapBalancedThresholds:
    def test_detects_clap(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend(clock=TickClock())
        r = dsp.process_pcm16(make_clap_signal())
        assert r.is_clap is True, f"reason={r.reason} rms={r.rms:.4f} pr={r.peak_ratio:.2f} hf={r.hf_ratio:.2f}"

    def test_detects_clap_lower_amplitude(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend(clock=TickClock())
        r = dsp.process_pcm16(make_clap_signal(peak_val=0.42, n_impulse=200))
        assert r.is_clap is True, f"reason={r.reason} rms={r.rms:.4f} pr={r.peak_ratio:.2f} hf={r.hf_ratio:.2f}"

    def test_rejects_silence(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend(clock=TickClock())
        assert dsp.process_pcm16(SILENCE_80).is_clap is False

    def test_rejects_continuous_noise(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend(clock=TickClock())
        r = dsp.process_pcm16(make_continuous_noise(amp=0.03))
        assert r.is_clap is False

    def test_cooldown_allows_sequential(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "120")
        from engine.dsp_clap_backend import DspClapBackend
        clk = TickClock(step=0.08)
        dsp = DspClapBackend(clock=clk)
        r1 = dsp.process_pcm16(make_clap_signal())
        assert r1.is_clap is True, f"first: {r1.reason}"
        clk._t += 0.16
        r2 = dsp.process_pcm16(make_clap_signal())
        assert r2.is_clap is True, f"second: {r2.reason}"

    def test_cooldown_blocks_immediate_second(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "120")
        from engine.dsp_clap_backend import DspClapBackend
        clk = TickClock(step=0.08)
        dsp = DspClapBackend(clock=clk)
        r1 = dsp.process_pcm16(make_clap_signal())
        assert r1.is_clap is True
        r2 = dsp.process_pcm16(make_clap_signal())
        assert r2.is_clap is False
        assert r2.reason.startswith("cooldown")
