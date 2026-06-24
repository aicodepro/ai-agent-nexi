import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.dsp_clap_backend import DspClapBackend


def _make_speech_like_pcm(length_samples=320):
    import struct
    samples = []
    for i in range(length_samples):
        val = int(5000 * (i % 40) / 40)
        samples.append(max(-32768, min(32767, val)))
    return struct.pack(f"<{len(samples)}h", *samples)


def test_speech_is_not_clap():
    backend = DspClapBackend(sample_rate=16000)
    backend._rms_threshold = 0.045
    backend._peak_threshold = 0.14
    backend._peak_ratio_threshold = 5.2
    backend._hf_ratio_threshold = 0.43

    pcm = _make_speech_like_pcm(320)
    result = backend.process_pcm16(pcm)
    assert result.is_clap is False
