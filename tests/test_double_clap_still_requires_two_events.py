"""Test double-clap logic still requires two separate events, not one."""

import time
import struct
import pytest


def test_single_clap_no_wake(monkeypatch):
    """Single clap event must NOT produce wake=True."""
    from engine.clap_backend_manager import ClapBackendManager

    class FakeClapNN:
        def __init__(self):
            self._ready = True
            self.call_count = 0
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            self.call_count += 1
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts,
                                reason="clap_detected")

    m = ClapBackendManager(clock=time.time, cooldown_ms=0)
    m._primary = FakeClapNN()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1280))
    result = m.process_audio_chunk(frame)
    assert not result["wake"], "Single clap must not trigger wake"
    assert result["clap"], "Single clap must show clap=True"


def test_two_claps_within_gap_triggers_wake():
    """Two clap events 400ms apart must trigger wake."""
    from engine.clap_backend_manager import ClapBackendManager

    fake_time = [1000.0]

    class FakeClapNN:
        def __init__(self):
            self._ready = True
            self.call_count = 0
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            self.call_count += 1
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts,
                                reason="clap_detected")

    def clock():
        return fake_time[0]

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapNN()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1280))

    # First clap
    fake_time[0] = 1000.0
    r1 = m.process_audio_chunk(frame)
    assert not r1["wake"]
    assert r1["clap"]

    # Second clap 400ms later
    fake_time[0] = 1000.4
    r2 = m.process_audio_chunk(frame)
    assert r2["wake"], "Two claps 400ms apart must trigger wake"
    assert r2["source"] == "double_clap"


def test_two_claps_too_soon_no_wake():
    """Two clap events 50ms apart must NOT trigger wake (too soon)."""
    from engine.clap_backend_manager import ClapBackendManager

    fake_time = [1000.0]

    class FakeClapNN:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts,
                                reason="clap_detected")

    def clock():
        return fake_time[0]

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapNN()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1280))

    fake_time[0] = 1000.0
    r1 = m.process_audio_chunk(frame)
    assert not r1["wake"]

    fake_time[0] = 1000.05  # 50ms gap
    r2 = m.process_audio_chunk(frame)
    assert not r2["wake"], "50ms gap must not trigger wake"


def test_two_claps_too_late_resets():
    """Two clap events 2000ms apart must reset state (too late)."""
    from engine.clap_backend_manager import ClapBackendManager

    fake_time = [1000.0]

    class FakeClapNN:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=True, confidence=0.95, timestamp=ts,
                                reason="clap_detected")

    def clock():
        return fake_time[0]

    m = ClapBackendManager(clock=clock, cooldown_ms=0)
    m._primary = FakeClapNN()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1280))

    fake_time[0] = 1000.0
    r1 = m.process_audio_chunk(frame)
    assert not r1["wake"]

    fake_time[0] = 1003.0  # 3000ms gap > 900ms max
    r2 = m.process_audio_chunk(frame)
    assert not r2["wake"], "3000ms gap must not trigger wake"
    assert r2["clap"], "Should still report clap detection"

    # After reset, third clap starts as new first, fourth completes double
    fake_time[0] = 1003.4  # 400ms after the too-late clap — new first clap
    r3 = m.process_audio_chunk(frame)
    assert not r3["wake"], "Third clap is new first, must not wake"

    fake_time[0] = 1003.8  # 400ms gap from third — valid double clap
    r4 = m.process_audio_chunk(frame)
    assert r4["wake"], "After reset, valid gap must trigger wake"


def test_speech_no_clap_event():
    """Speech must not produce clap events at all."""
    from engine.clap_backend_manager import ClapBackendManager

    class FakeClapNN:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=False, confidence=0.05, timestamp=ts,
                                reason="speech_or_noise")

    m = ClapBackendManager(clock=time.time, cooldown_ms=0)
    m._primary = FakeClapNN()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    frame = struct.pack("<1280h", *([0] * 1280))
    for _ in range(5):
        result = m.process_audio_chunk(frame)
        assert not result["clap"], "Speech must not report clap=True"
        assert not result["wake"], "Speech must not trigger wake"
