"""Tests: ClapBackendManager fallback order when primary fails."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestClapBackendFallbackOrder:
    def test_dsp_clap_fallback_when_clap_nn_missing(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        assert mgr.primary_name == "dsp_clap"
        assert mgr.primary_ready is True
        assert mgr.fallback_name == "clap_nn"
        assert mgr.fallback_ready is False

    def test_fallback_order_used_when_primary_not_ready(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "clap_nn,dsp_clap")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        assert mgr.primary_name == "clap_nn"
        assert mgr.primary_ready is False
        assert mgr.fallback_name == "dsp_clap"
        assert mgr.fallback_ready is True

    def test_fallback_detects_clap_when_primary_missing(self, monkeypatch):
        import struct
        monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "clap_nn,dsp_clap")
        monkeypatch.setenv("JARVIS_CLAP_DEBUG", "true")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)

        samples = [0] * 800
        for i in range(5):
            idx = 400 + i
            if idx < len(samples):
                samples[idx] = 20000
        for i in range(5):
            idx = 405 + i
            if idx < len(samples):
                samples[idx] = -18000
        clap_bytes = struct.pack(f"<{len(samples)}h", *samples)

        r = mgr.process_audio_chunk(clap_bytes)
        assert r.get("clap") is True
        assert r.get("backend") == "dsp_clap"

    def test_all_backends_fail_does_not_crash(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "yamnet,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        assert mgr.primary_ready is False
        assert mgr.fallback_ready is False

        r = mgr.process_audio_chunk(b"\x00\x00" * 1280)
        assert r.get("clap") is False
        assert r.get("wake") is False
        assert r.get("backend") == "none"

    def test_hotword_still_works_when_all_clap_backends_fail(self, monkeypatch):
        monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "yamnet,clap_nn")
        monkeypatch.setenv("JARVIS_HOTWORD_ENABLED", "true")
        from engine.hotword_engine_manager import HotwordEngineManager
        hwm = HotwordEngineManager({"enabled": True, "debug": False})
        r = hwm.process_audio_chunk(b"\x00\x00" * 1280, 16000)
        assert r.detected is False
        assert r.engine == "openwakeword"
