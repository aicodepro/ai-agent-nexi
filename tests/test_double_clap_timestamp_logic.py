"""Test double-clap timestamp logic in ClapBackendManager."""

import struct
import time
import pytest


class FakeClock:
    """A controllable clock for testing timing-dependent behavior."""
    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float):
        self._now += seconds


def test_first_clap_no_wake():
    """A single clap must not trigger wake."""
    from engine.clap_backend_manager import ClapBackendManager

    clock = FakeClock(0.0)

    class FakeClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))
    r = m.process_audio_chunk(frame)
    assert not r["wake"], "First clap must not wake"
    assert r["clap"], "First clap must set clap=True"
    state = m._double_clap.get_status()["state"]
    assert state in ("stage_first_clap", "first_clap_waiting"), f"Expected waiting state, got {state}"


def test_double_clap_within_gap_wakes():
    """Two claps 400ms apart must trigger wake."""
    from engine.clap_backend_manager import ClapBackendManager

    clock = FakeClock(0.0)

    class FakeClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))

    # First clap at t=0
    r1 = m.process_audio_chunk(frame)
    assert not r1["wake"]
    assert r1["clap"]

    # Second clap at t=0.4 (400ms gap)
    clock.advance(0.4)
    r2 = m.process_audio_chunk(frame)
    assert r2["wake"], "Double clap within gap must wake"
    assert r2["source"] == "double_clap"


def test_double_clap_too_soon_no_wake():
    """Two claps 50ms apart must not wake (same acoustic event)."""
    from engine.clap_backend_manager import ClapBackendManager

    clock = FakeClock(0.0)

    class FakeClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))

    r1 = m.process_audio_chunk(frame)
    assert not r1["wake"]

    clock.advance(0.05)  # 50ms — too soon
    r2 = m.process_audio_chunk(frame)
    assert not r2["wake"], "Claps too close must not wake"


def test_double_clap_too_late_no_wake():
    """Two claps 2s apart must not wake (too late, reset)."""
    from engine.clap_backend_manager import ClapBackendManager

    clock = FakeClock(0.0)

    class FakeClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))

    r1 = m.process_audio_chunk(frame)
    assert not r1["wake"]

    clock.advance(2.0)  # 2s — too late
    r2 = m.process_audio_chunk(frame)
    assert not r2["wake"], "Claps too far apart must not wake"
    # After too-late second clap, state resets; next clap becomes new first
    state = m._double_clap.get_status()["state"]
    assert state == "reset", f"Expected reset state, got {state}"


def test_cooldown_after_double_clap():
    """After wake, must respect cooldown before next wake."""
    from engine.clap_backend_manager import ClapBackendManager

    clock = FakeClock(0.0)

    class FakeClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts)

    m = ClapBackendManager(clock=clock, cooldown_ms=2000)
    m._primary = FakeClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1000 + [30000] * 280))

    # First double clap
    r1 = m.process_audio_chunk(frame)
    clock.advance(0.4)
    r2 = m.process_audio_chunk(frame)
    assert r2["wake"]

    # Immediately try again — should be in cooldown
    r3 = m.process_audio_chunk(frame)
    assert r3.get("cooldown", False) or not r3["wake"]

    # After cooldown passes, should allow new double clap
    clock.advance(3.0)
    r4 = m.process_audio_chunk(frame)
    clock.advance(0.4)
    r5 = m.process_audio_chunk(frame)
    assert r5["wake"], "Should wake after cooldown"
