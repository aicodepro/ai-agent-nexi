import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.dsp_clap_backend import DspClapBackend


def _make_silence_pcm(length_samples=320):
    import struct
    samples = [0] * length_samples
    return struct.pack(f"<{len(samples)}h", *samples)


def test_silence_is_not_clap():
    backend = DspClapBackend(sample_rate=16000)
    pcm = _make_silence_pcm(320)
    result = backend.process_pcm16(pcm)
    assert result.is_clap is False


def test_silence_reason_is_low_rms():
    backend = DspClapBackend(sample_rate=16000)
    backend._rms_threshold = 0.001
    pcm = _make_silence_pcm(320)
    result = backend.process_pcm16(pcm)
    assert result.is_clap is False
