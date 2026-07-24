"""Tests: Double clap with DSP backend requires two events, single clap never wakes."""

import math
import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_clap_impulse():
    """HF-rich impulse (broadband tone burst), same shape as
    test_double_clap_gap_window.py's make_clap_signal(). The dsp_clap
    hf_ratio check is derivative-based (sample-to-sample delta energy), so a
    flat constant-amplitude plateau has ~0 high-frequency content and is
    rejected regardless of peak_ratio; a real transient needs actual
    sample-to-sample variation to register as high-frequency energy.
    """
    total = 1280
    samples = [0] * total
    start = total * 3 // 4
    for i in range(200):
        idx = start + i
        if idx >= total:
            break
        val = (math.sin(2 * math.pi * 3500 * i / 16000.0) * 0.4 +
               math.sin(2 * math.pi * 5000 * i / 16000.0) * 0.4) * (1.0 - i / 200) * 0.6
        samples[idx] = int(val * 32767)
    return struct.pack(f"<{len(samples)}h", *samples)


def _make_silence():
    return b"\x00\x00" * 1600


class TestDoubleClapFastBackends:
    def test_single_clap_no_wake_with_dsp_backend(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        r = mgr.process_audio_chunk(_make_clap_impulse())
        assert r.get("clap") is True
        assert r.get("wake") is False

    def test_two_claps_within_gap_triggers_wake(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "0")
        from engine.clap_backend_manager import ClapBackendManager

        clock = [1000.0]
        def fake_clock():
            return clock[0]

        mgr = ClapBackendManager(clock=fake_clock, cooldown_ms=5000)
        mgr._min_gap_ms = 180.0
        mgr._max_gap_ms = 900.0

        # First clap
        r1 = mgr.process_audio_chunk(_make_clap_impulse())
        assert r1.get("clap") is True
        assert r1.get("wake") is False
        state = mgr._double_clap.get_status()["state"]
        assert state in ("stage_first_clap", "first_clap_waiting"), f"Expected waiting state, got {state}"

        # Second clap after 500ms — within gap
        clock[0] = 1000.5
        r2 = mgr.process_audio_chunk(_make_clap_impulse())
        assert r2.get("clap") is True
        assert r2.get("wake") is True
        assert r2.get("source") == "double_clap"

    def test_two_claps_too_soon_no_wake(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "0")
        from engine.clap_backend_manager import ClapBackendManager

        clock = [1000.0]
        def fake_clock():
            return clock[0]

        mgr = ClapBackendManager(clock=fake_clock, cooldown_ms=5000)
        mgr._min_gap_ms = 180.0
        mgr._max_gap_ms = 900.0

        r1 = mgr.process_audio_chunk(_make_clap_impulse())
        assert r1.get("wake") is False

        clock[0] = 1000.1  # 100ms gap — too soon (DSP backend may not detect second clap)
        r2 = mgr.process_audio_chunk(_make_clap_impulse())
        assert r2.get("wake") is False
        state = mgr._double_clap.get_status()["state"]
        # DSP backend may not detect a second clap this close, leaving state at stage_first_clap.
        # FakeClapBackend tests in test_double_clap_timestamp_logic.py verify the too-soon reset logic.
        assert state in ("stage_first_clap", "reset"), f"Unexpected state: {state}"

    def test_two_claps_too_late_resets(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        monkeypatch.setenv("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "0")
        from engine.clap_backend_manager import ClapBackendManager

        clock = [1000.0]
        def fake_clock():
            return clock[0]

        mgr = ClapBackendManager(clock=fake_clock, cooldown_ms=5000)
        mgr._min_gap_ms = 180.0
        mgr._max_gap_ms = 900.0

        r1 = mgr.process_audio_chunk(_make_clap_impulse())
        assert r1.get("wake") is False

        clock[0] = 1002.0  # 1000ms gap — too late
        r2 = mgr.process_audio_chunk(_make_clap_impulse())
        assert r2.get("wake") is False
        # Should reset; next clap becomes new first
        assert mgr._double_clap.get_status()["state"] == "reset"

    def test_speech_not_detected_as_clap(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager

        mgr = ClapBackendManager(cooldown_ms=5000)

        # Sustained energy (speech-like)
        samples = [3000] * 3200
        speech_bytes = struct.pack(f"<{len(samples)}h", *samples)
        r = mgr.process_audio_chunk(speech_bytes)
        # Should not be clap (low peak ratio, low HF ratio, too long)
        assert r.get("clap") is False

    def test_silence_not_detected_as_clap(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        r = mgr.process_audio_chunk(_make_silence())
        assert r.get("clap") is False
        assert r.get("wake") is False
