"""Tests: DSP clap backend rejects low-peak noise (no transient = not clap)."""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDspClapRejectsLowPeakNoise:
    def test_low_peak_noise_is_not_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        samples = [5000] * 800
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False
        assert "low_ratio" in r.reason

    def test_no_transient_no_clap_even_with_moderate_rms(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        samples = [4000] * 800
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False
        assert "low_ratio" in r.reason

    def test_gradual_attack_not_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        samples = [0] * 800
        for i in range(400, 800):
            samples[i] = int(30000 * (i - 399) / 400)
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False
        # Should be rejected by peak ratio or sustained speech detection

    def test_brown_noise_not_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        samples = [0] * 800
        val = 0
        for i in range(800):
            val += 200
            if val > 32767:
                val = 32767
            samples[i] = val
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False

    def test_low_peak_noise_not_clap_through_manager(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)

        samples = [4000] * 800
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = mgr.process_audio_chunk(data)
        assert r.get("clap") is False
        assert r.get("wake") is False
