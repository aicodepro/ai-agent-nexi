import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _clap_frame():
    samples = np.zeros(1280, dtype=np.int16)
    samples[380:700] = 30000
    return samples.tobytes()


def test_tzur_double_clap_requires_real_gap():
    from engine.tzur_clap_adapter import TzurClapAdapter

    clock = FakeClock()
    adapter = TzurClapAdapter(clock=clock, threshold_bias=0.01, min_amplitude=0.02, debounce_ms=0, min_clap_gap_ms=180)
    first = adapter.process_audio_chunk(_clap_frame())
    assert first["clap"] is True
    assert first["wake"] is False

    clock.advance(0.42)
    second = adapter.process_audio_chunk(_clap_frame())
    assert second["wake"] is True
    assert second["source"] == "double_clap"
    assert 180 <= second["gap_ms"] <= 900
