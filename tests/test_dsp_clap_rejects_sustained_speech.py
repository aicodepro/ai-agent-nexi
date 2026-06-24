"""Tests: DSP clap backend rejects sustained speech-like noise."""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDspClapRejectsSustainedSpeech:
    def test_sustained_speech_is_not_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        frames = b""
        for _ in range(10):
            samples = [6000] * 1600
            frames += struct.pack(f"<{len(samples)}h", *samples)

        for offset in range(0, len(frames), 3200):
            chunk = frames[offset:offset + 3200]
            r = dsp.process_pcm16(chunk)
            assert r.is_clap is False

    def test_sustained_speech_no_wake_through_manager(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)

        for _ in range(10):
            samples = [5000] * 1600
            data = struct.pack(f"<{len(samples)}h", *samples)
            r = mgr.process_audio_chunk(data)
            assert r.get("wake") is False
            assert r.get("clap") is False

    def test_changing_pitch_no_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        import math
        samples = [0] * 1600
        for i in range(1600):
            freq = 200 + int(50 * math.sin(2 * math.pi * i / 1600))
            samples[i] = int(8000 * math.sin(2 * math.pi * freq * i / 16000))
        data = struct.pack(f"<{len(samples)}h", *samples)
        r = dsp.process_pcm16(data)
        assert r.is_clap is False

    def test_multiple_phrases_no_clap(self):
        from engine.dsp_clap_backend import DspClapBackend
        dsp = DspClapBackend()

        import math
        for phrase_len in [800, 1600, 3200]:
            samples = [0] * phrase_len
            for i in range(phrase_len):
                envelope = 1.0 - abs(i - phrase_len / 2) / (phrase_len / 2)
                samples[i] = int(12000 * max(0, envelope) * math.sin(2 * math.pi * 250 * i / 16000))
            data = struct.pack(f"<{len(samples)}h", *samples)
            r = dsp.process_pcm16(data)
            assert r.is_clap is False

    def test_rapid_speech_no_clap_wake(self, monkeypatch):
        monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000, clock=lambda: 0.0)

        import math
        for start_time in [0.0, 0.2, 0.4, 0.6, 0.8]:
            mgr._clock = lambda: start_time
            samples = [0] * 1600
            for i in range(1600):
                samples[i] = int(10000 * math.sin(2 * math.pi * 300 * i / 16000))
            data = struct.pack(f"<{len(samples)}h", *samples)
            r = mgr.process_audio_chunk(data)
            assert r.get("wake") is False
