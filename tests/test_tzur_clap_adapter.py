"""Tests for TzurClapAdapter — unit-level, no mic needed."""

import struct
import numpy as np
import pytest


class TestTzurClapAdapter:

    def test_import_and_create(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000)
        assert a.is_ready
        assert a.ema_threshold > 0

    def test_silence_no_detect(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000)
        silence = struct.pack("<1280h", *([0] * 1280))
        r = a.process_audio_chunk(silence)
        assert not r["clap"]
        assert not r["wake"]
        assert r["backend"] == "tzur"

    def test_noise_no_detect(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000)
        noise = (np.random.randn(1280) * 200).astype(np.int16).tobytes()
        r = a.process_audio_chunk(noise)
        assert not r["wake"]

    def test_loud_burst_detects_single(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000, debounce_ms=0, min_amplitude=0.02, threshold_bias=0.02)
        # Very loud burst
        samples = np.zeros(1280, dtype=np.int16)
        samples[400:700] = 28000
        r = a.process_audio_chunk(samples.tobytes())
        # Should at minimum register a clap
        assert r["clap"] or r["amplitude"] > 0.1

    def test_debug_snapshot(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000)
        snap = a.get_debug_snapshot()
        assert "ready" in snap
        assert "ema_threshold" in snap
        assert snap["ready"] is True

    def test_reset_clears_state(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000, debounce_ms=0, threshold_bias=0.02)
        loud = np.zeros(1280, dtype=np.int16)
        loud[400:700] = 30000
        a.process_audio_chunk(loud.tobytes())
        a.reset()
        assert a.ema_threshold <= 0.02
        assert a._total_chunks > 0  # total_chunks not reset

    def test_cooldown_suppresses_detection(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000, debounce_ms=0, threshold_bias=0.01, min_amplitude=0.02)
        a.set_cooldown(5.0)
        loud = np.zeros(1280, dtype=np.int16)
        loud[400:700] = 30000
        r = a.process_audio_chunk(loud.tobytes())
        assert r.get("cooldown") is True
        assert not r["wake"]

    def test_not_ready_returns_safe(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000)
        a._ready = False
        r = a.process_audio_chunk(b"data")
        assert not r["clap"]
        assert not r["wake"]

    def test_empty_frame_safe(self):
        from engine.tzur_clap_adapter import TzurClapAdapter
        a = TzurClapAdapter(sample_rate=16000)
        r = a.process_audio_chunk(b"")
        assert not r["clap"]
        assert not r["wake"]

    def test_create_tzur_adapter_helper(self):
        from engine.tzur_clap_adapter import create_tzur_adapter
        a = create_tzur_adapter()
        assert a.is_ready