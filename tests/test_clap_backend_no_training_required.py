"""Tests: runtime does NOT block when CLAP_NN model is missing.

The DSP clap backend should load and work without any training data.
"""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _stable_dsp_thresholds(monkeypatch):
    monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.030")
    monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.10")
    monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "4.0")
    monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.30")


def _make_impulse(duration_samples: int = 800) -> bytes:
    samples = [0] * duration_samples
    for i in range(20):
        idx = duration_samples // 2 + i
        if idx < duration_samples:
            samples[idx] = 20000 if i % 2 == 0 else -18000
    return struct.pack(f"<{len(samples)}h", *samples)


class TestClapBackendNoTrainingRequired:
    def test_dsp_backend_works_without_clap_nn_model(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()
        r = dsp.process_pcm16(_make_impulse())
        assert r.is_clap is True
        assert r.confidence > 0.5

    def test_manager_falls_back_to_dsp_when_clap_nn_missing(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        monkeypatch.setenv("NEXI_CLAP_DEBUG", "true")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        assert mgr.primary_name == "dsp_clap"
        assert mgr.primary_ready is True
        assert mgr.fallback_name == "clap_nn"
        assert mgr.fallback_ready is False

    def test_manager_dsp_detects_single_clap_no_wake(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        monkeypatch.setenv("NEXI_CLAP_DEBUG", "true")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        r = mgr.process_audio_chunk(_make_impulse())
        assert r.get("clap") is True
        assert r.get("wake") is False
        assert r.get("backend") == "dsp_clap"

    def test_manager_still_processes_if_clap_nn_model_missing(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "clap_nn,dsp_clap")
        monkeypatch.setenv("NEXI_CLAP_DEBUG", "true")
        from engine.clap_backend_manager import ClapBackendManager
        monkeypatch.setattr(ClapBackendManager, "_build_clap_nn", lambda self: (None, False))
        mgr = ClapBackendManager(cooldown_ms=5000)
        assert mgr.primary_ready is False
        assert mgr.fallback_ready is True
        r = mgr.process_audio_chunk(_make_impulse())
        assert r.get("clap") is True or r.get("backend") == "dsp_clap"

    def test_manager_status_shows_dsp(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        status = mgr.get_status()
        assert status["primary"] == "dsp_clap"
        assert status["primary_ready"] is True
        assert status["fallback"] == "clap_nn"
        assert status["fallback_ready"] is False
