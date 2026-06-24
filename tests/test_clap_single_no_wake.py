import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_single_clap_does_not_wake_tzur():
    from engine.tzur_clap_adapter import TzurClapAdapter

    samples = np.zeros(1280, dtype=np.int16)
    samples[400:720] = 30000
    adapter = TzurClapAdapter(threshold_bias=0.01, min_amplitude=0.02, debounce_ms=0)
    result = adapter.process_audio_chunk(samples.tobytes())
    assert result["clap"] is True
    assert result["wake"] is False
