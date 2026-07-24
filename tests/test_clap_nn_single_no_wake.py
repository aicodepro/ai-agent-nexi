"""Test CLAP_NN single clap never triggers wake.

Single clap (even high-confidence) must never wake.
Only double clap within valid timestamp gap wakes.
"""

import struct
import pytest


def test_single_clap_no_wake():
    """Without trained model, a single clap-like frame must not wake."""
    from engine.clap_nn_backend import ClapNNBackend
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    frame = struct.pack("<16000h", *([0] * 12000 + [32767] * 4000))
    result = backend.process_pcm16(frame, 0.0)
    assert not result.is_clap


def test_multiple_clap_like_frames_still_no_wake():
    """Multiple single clap frames must not wake through backend alone."""
    from engine.clap_nn_backend import ClapNNBackend
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    clap = struct.pack("<16000h", *([0] * 14000 + [30000] * 2000))
    for i in range(5):
        result = backend.process_pcm16(clap, float(i) * 0.3)
        assert not result.is_clap, f"Frame {i} should not be clap without model"


def test_backend_manager_single_clap_no_wake():
    """ClapBackendManager must not wake on a single clap event."""
    from engine.clap_backend_manager import ClapBackendManager

    class FakeSingleClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(cooldown_ms=0)
    m._primary = FakeSingleClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))
    r = m.process_audio_chunk(frame)
    assert not r["wake"], "Single clap must not wake via manager"
    assert r["clap"], "Single clap should still report clap=True"


def test_backend_manager_single_clap_no_wake_multiple_calls():
    """Even with repeated single claps, must never wake without second clap timing."""
    import time
    from engine.clap_backend_manager import ClapBackendManager

    class FakeSingleClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(cooldown_ms=0)
    m._primary = FakeSingleClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))

    for i in range(10):
        r = m.process_audio_chunk(frame)
        if i == 0:
            assert not r["wake"], f"First call must not wake: call {i}"
        else:
            # After first clap, subsequent single claps might reset or become new first
            # But must NEVER wake without a pair
            pass
        # Verify no wake ever
        assert not r["wake"] or False  # sanity
        # Actually, let's check properly:
        if i == 0:
            assert r["clap"] and not r["wake"]

    # Final assertion: no wake ever occurred
    assert not any(m.process_audio_chunk(frame).get("wake", False)
                   for _ in range(3)), "Repeated single claps must never wake"
