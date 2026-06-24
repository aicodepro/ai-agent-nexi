"""Tests: double-clap is not blocked by DSP event cooldown."""

import math
import os
import struct
import sys
import time as time_module

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def make_clap_signal(peak_val: float = 0.5, n_impulse: int = 200, total: int = 1280):
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


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self._t = start
    def __call__(self):
        return self._t
    def advance(self, sec: float):
        self._t += sec


class TestDoubleClapNotBlockedByEventCooldown:
    def test_cooldown_allows_fast_second_clap(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "120")
        from engine.dsp_clap_backend import DspClapBackend
        clk = FakeClock()
        dsp = DspClapBackend(clock=clk)
        r1 = dsp.process_pcm16(make_clap_signal())
        assert r1.is_clap is True
        clk.advance(0.16)
        r2 = dsp.process_pcm16(make_clap_signal())
        assert r2.is_clap is True, f"second: {r2.reason}"

    def test_dsp_cooldown_does_not_block_manager(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "120")
        monkeypatch.setenv("NEXI_CLAP_MIN_GAP_MS", "160")
        monkeypatch.setenv("NEXI_CLAP_MAX_GAP_MS", "950")
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap")
        clk = FakeClock()
        monkeypatch.setattr(time_module, "time", clk)
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=2000, clock=clk)
        r1 = mgr.process_audio_chunk(make_clap_signal())
        assert r1.get("clap") is True, f"first: {r1}"
        assert r1.get("wake") is False
        clk.advance(0.24)
        r2 = mgr.process_audio_chunk(make_clap_signal())
        assert r2.get("wake") is True, f"second: {r2}"

    def test_wide_gap_allows_double_clap(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_CLAP_MIN_GAP_MS", "160")
        monkeypatch.setenv("NEXI_CLAP_MAX_GAP_MS", "950")
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap")
        clk = FakeClock()
        monkeypatch.setattr(time_module, "time", clk)
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=2000, clock=clk)
        r1 = mgr.process_audio_chunk(make_clap_signal())
        assert r1.get("clap") is True
        assert r1.get("wake") is False
        clk.advance(0.32)
        r2 = mgr.process_audio_chunk(make_clap_signal())
        assert r2.get("wake") is True

    def test_varying_gap_allows_double_clap(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_CLAP_MIN_GAP_MS", "160")
        monkeypatch.setenv("NEXI_CLAP_MAX_GAP_MS", "950")
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap")
        clk = FakeClock()
        monkeypatch.setattr(time_module, "time", clk)
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=2000, clock=clk)
        for gap_sec in (0.17, 0.24, 0.40):
            mgr.reset()
            clk.advance(10.0)
            r1 = mgr.process_audio_chunk(make_clap_signal())
            assert r1.get("clap") is True
            assert r1.get("wake") is False
            clk.advance(gap_sec)
            r2 = mgr.process_audio_chunk(make_clap_signal())
            assert r2.get("wake") is True, f"gap={gap_sec}"

    def test_single_clap_rejected_by_manager(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
        monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
        monkeypatch.setenv("NEXI_CLAP_MIN_GAP_MS", "160")
        monkeypatch.setenv("NEXI_CLAP_MAX_GAP_MS", "950")
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap")
        clk = FakeClock()
        monkeypatch.setattr(time_module, "time", clk)
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=2000, clock=clk)
        r = mgr.process_audio_chunk(make_clap_signal())
        assert r.get("clap") is True
        assert r.get("wake") is False
        clk.advance(5.0)
        r2 = mgr.process_audio_chunk(make_clap_signal())
        assert r2.get("clap") is True
        assert r2.get("wake") is False
