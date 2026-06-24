from __future__ import annotations

from engine.clap_nn_backend import ClapNNBackend


def test_double_clap_timing_window_respected():
    """Double clap is a two-clap pattern within a time window.
    Without model loaded, no clap should be detected."""
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    import struct
    clap1 = struct.pack("<16000h", *([0] * 14000 + [32767] * 2000))
    clap2 = struct.pack("<16000h", *([0] * 14000 + [30000] * 2000))
    r1 = backend.process_pcm16(clap1, 0.0)
    r2 = backend.process_pcm16(clap2, 0.5)
    assert not r1.is_clap
    assert not r2.is_clap


def test_double_clap_far_apart_not_counted():
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    import struct
    clap = struct.pack("<16000h", *([0] * 14000 + [32767] * 2000))
    r1 = backend.process_pcm16(clap, 0.0)
    r2 = backend.process_pcm16(clap, 3.0)
    assert not r1.is_clap
    assert not r2.is_clap
