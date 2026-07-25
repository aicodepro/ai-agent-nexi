"""Tests for ClapBackendManager — unit-level, no mic needed."""

import struct
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _stable_backend_order(monkeypatch):
    monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")


class TestClapBackendManager:

    def test_import_and_create(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=100)
        status = m.get_status()
        assert "primary" in status
        assert "fallback" in status

    def test_primary_is_dsp_clap_by_default(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=5000)
        assert m.primary_name == "dsp_clap"

    def test_fallback_is_clap_nn_by_default(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=5000)
        assert m.fallback_name == "clap_nn"

    def test_silence_no_wake(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=0)
        silence = struct.pack("<1280h", *([0] * 1280))
        r = m.process_audio_chunk(silence)
        assert not r["wake"]

    def test_noise_no_wake(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=0)
        noise = (np.random.randn(1280) * 200).astype(np.int16).tobytes()
        r = m.process_audio_chunk(noise)
        assert not r["wake"]

    def test_get_status(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=5000)
        status = m.get_status()
        assert status["primary"] == "dsp_clap"
        assert status["fallback"] == "clap_nn"

    def test_debug_snapshot(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager()
        snap = m.get_debug_snapshot()
        assert "primary" in snap
        assert "primary_ready" in snap
        assert "fallback_ready" in snap

    def test_reset_does_not_crash(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager()
        m.reset()

    def test_cooldown_prevents_detection(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=99999)
        r = m.process_audio_chunk(b"\x00" * 2560)
        assert r["cooldown"] is True or not r["wake"]

    def test_create_backend_manager_helper(self):
        from engine.clap_backend_manager import create_backend_manager
        m = create_backend_manager()
        status = m.get_status()
        assert "primary" in status

    def test_backend_uses_none_when_no_wake(self):
        from engine.clap_backend_manager import ClapBackendManager
        m = ClapBackendManager(cooldown_ms=0)
        silence = struct.pack("<1280h", *([0] * 1280))
        r = m.process_audio_chunk(silence)
        assert r["backend"] == "none"
        assert not r["wake"]

    def test_legacy_jarvis_gap_and_cooldown_env_aliases(self, monkeypatch):
        from engine.clap_backend_manager import ClapBackendManager

        for key in (
            "NEXI_CLAP_MIN_GAP_MS",
            "CLAP_MIN_GAP_MS",
            "NEXI_CLAP_MAX_GAP_MS",
            "CLAP_MAX_GAP_MS",
            "NEXI_CLAP_COOLDOWN_MS",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("JARVIS_CLAP_MIN_GAP_MS", "140")
        monkeypatch.setenv("JARVIS_CLAP_MAX_GAP_MS", "4700")
        monkeypatch.setenv("JARVIS_CLAP_COOLDOWN_MS", "1700")

        status = ClapBackendManager().get_status()

        assert status["min_gap_ms"] == 140
        assert status["max_gap_ms"] == 4700
        assert status["cooldown_ms"] == 1700
