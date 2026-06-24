"""Tests: DSP clap backend rejects silence (no false clap in quiet)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDspClapRejectsSilence:
    def test_silence_is_not_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(b"\x00\x00" * 1600)
        assert r.is_clap is False

    def test_silence_returns_low_rms_reason(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(b"\x00\x00" * 1600)
        assert "low_rms" in r.reason

    def test_silence_confidence_zero(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(b"\x00\x00" * 1600)
        assert r.confidence == 0.0

    def test_near_silence_low_amplitude_also_rejected(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        samples = [40] * 1600
        import struct
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False

    def test_repeated_silence_does_not_accumulate(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        for _ in range(10):
            r = dsp.process_pcm16(b"\x00\x00" * 1600)
            assert r.is_clap is False
            assert r.reason != "cooldown"

    def test_silence_no_false_wake_through_manager(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        for _ in range(20):
            r = mgr.process_audio_chunk(b"\x00\x00" * 1600)
            assert r.get("wake") is False
            assert r.get("clap") is False
