"""Tests: hotword runtime is NOT blocked by missing clap model.

Hotword (openWakeWord) and clap (DSP) are independent. If one fails,
the other should still work.
"""

import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_silence(duration_samples: int = 1600) -> bytes:
    return b"\x00\x00" * duration_samples


class TestHotwordNotBlockedByClapTraining:
    def test_openwakeword_imports_without_clap_model(self):
        from engine.hotword_engine_manager import HotwordEngineManager
        hwm = HotwordEngineManager({"enabled": True, "debug": False})
        assert hwm.enabled is True
        status = hwm.get_status()
        assert status["engine"] == "openwakeword"

    def test_hotword_returns_result_without_clap(self):
        from engine.hotword_engine_manager import HotwordEngineManager
        hwm = HotwordEngineManager({"enabled": True, "debug": False})
        r = hwm.process_audio_chunk(_make_silence(), 16000)
        assert r.detected is False
        assert r.engine == "openwakeword"
        assert r.phrase != ""

    def test_audio_wake_pipeline_does_not_crash_on_missing_model(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "clap_nn,dsp_clap")
        monkeypatch.setenv("NEXI_CLAP_DEBUG", "true")
        from engine.audio_wake_pipeline import AudioWakePipeline
        from engine.wake_orchestrator import WakeOrchestrator
        pipeline = AudioWakePipeline(enable_clap=True)
        result = pipeline.process_frame(_make_silence())
        assert result is not None
        assert "wake" in result
