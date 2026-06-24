import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class Clock:
    def __init__(self):
        self.now = 100.0
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


def _clap_frame(n=1024, amp=30000):
    samples = [0] * 512 + [amp] * 128 + [0] * 384
    return struct.pack(f"<{len(samples)}h", *samples)


def _long_speech_like_frame(n=1024, amp=20000):
    return struct.pack(f"<{n}h", *([amp] * n))


def test_double_clap_wakes_once():
    from engine.clap_detector import ClapStateMachine
    clock = Clock()
    sm = ClapStateMachine(clock=clock)
    assert sm.process_frame(_clap_frame())["wake"] is False
    clock.advance(0.3)
    assert sm.process_frame(_clap_frame())["wake"] is True


def test_clap_cooldown_blocks_spam():
    from engine.clap_detector import ClapStateMachine
    clock = Clock()
    sm = ClapStateMachine(clock=clock)
    sm.process_frame(_clap_frame())
    clock.advance(0.3)
    assert sm.process_frame(_clap_frame())["wake"] is True
    clock.advance(0.3)
    event = sm.process_frame(_clap_frame())
    assert event["cooldown"] is True
    assert event["wake"] is False


def test_clap_state_resets_after_wake():
    from engine.clap_detector import ClapStateMachine
    clock = Clock()
    sm = ClapStateMachine(clock=clock)
    sm.process_frame(_clap_frame())
    clock.advance(0.3)
    sm.process_frame(_clap_frame())
    assert sm.events == []


def test_speech_like_long_audio_ignored():
    from engine.clap_detector import is_clap_frame
    assert is_clap_frame(_long_speech_like_frame()) is False


def test_sustained_clap_frame_does_not_emit_repeated_first_claps():
    from engine.clap_detector import ClapStateMachine
    clock = Clock()
    sm = ClapStateMachine(clock=clock)
    first = sm.process_frame(_clap_frame())
    assert first["clap"] is True
    assert first["index"] == 1
    clock.advance(0.05)
    duplicate = sm.process_frame(_clap_frame())
    assert duplicate["clap"] is False
    assert duplicate["ignored"] is True
    assert duplicate["reason"] == "long_audio_or_cooldown"
    assert len(sm.events) == 1


def test_clap_state_names_are_explicit():
    from engine.clap_detector import ClapStateMachine
    clock = Clock()
    sm = ClapStateMachine(clock=clock)
    assert sm.state == "idle"
    first = sm.process_frame(_clap_frame())
    assert first["state"] == "first_clap_detected"
    clock.advance(0.3)
    second = sm.process_frame(_clap_frame())
    assert second["state"] == "wake_fired"
