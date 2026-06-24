"""Tests: speech must NOT be detected as clap by any backend."""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_speech_like(duration_frames: int = 1600, amplitude: int = 8000) -> bytes:
    """Sustained energy with low HF content (speech-vowel-like)."""
    samples = [0] * duration_frames
    for i in range(duration_frames):
        mod = (i % 80)
        if mod < 40:
            samples[i] = int(amplitude * (1.0 - mod / 40.0))
        else:
            samples[i] = int(-amplitude * (mod - 40) / 40.0)
    return struct.pack(f"<{len(samples)}h", *samples)


def _make_table_tap() -> bytes:
    """Low-amplitude short transient (table tap)."""
    samples = [0] * 800
    for i in range(5):
        samples[400 + i] = 12000
    return struct.pack(f"<{len(samples)}h", *samples)


class TestSpeechNotClapFastBackends:
    def test_dsp_backend_rejects_speech(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_speech_like(1600, 8000))
        assert r.is_clap is False

    def test_dsp_backend_rejects_sustained_noise(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        samples = [5000] * 3200
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False
        assert "low_ratio" in r.reason or "too_long" in r.reason

    def test_dsp_backend_rejects_table_tap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_table_tap())
        assert r.is_clap is False
        assert "low_rms" in r.reason or "low_peak_ratio" in r.reason

    def test_manager_rejects_speech_with_dsp_backend(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        r = mgr.process_audio_chunk(_make_speech_like(1600, 8000))
        assert r.get("clap") is False
        assert r.get("wake") is False

    def test_manager_silence_rejected(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        r = mgr.process_audio_chunk(b"\x00\x00" * 1600)
        assert r.get("clap") is False

    def test_dsp_hf_threshold_tunable(self, monkeypatch):
        monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.20")
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        # Speech-like with some HF content at lower threshold might trigger
        r = dsp.process_pcm16(_make_speech_like(1600, 8000))
        assert r.is_clap is False
