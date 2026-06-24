import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class Clock:
    def __init__(self):
        self.t = 1000.0
    def __call__(self):
        return self.t
    def advance(self, sec):
        self.t += sec


class Scores:
    def __init__(self, values):
        self.values = list(values)
        self.i = 0
    def __call__(self, audio):
        value = self.values[min(self.i, len(self.values) - 1)]
        self.i += 1
        return value


def frame():
    return struct.pack("<1280h", *([900] * 1280))


def test_first_valid_detection_not_blocked_by_rising_edge():
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"scorer": Scores([0.4]), "threshold": 0.25, "rising_edge_delta": 0.03})
    assert manager.process_audio_chunk(frame(), 16000).detected is True


def test_repeated_stuck_high_is_blocked_until_cooldown_expires():
    from engine.hotword_engine_manager import HotwordEngineManager

    clock = Clock()
    manager = HotwordEngineManager({
        "scorer": Scores([0.5, 0.5, 0.9]),
        "threshold": 0.25,
        "cooldown_ms": 1800,
        "clock": clock,
    })
    assert manager.process_audio_chunk(frame(), 16000).detected is True
    assert manager.process_audio_chunk(frame(), 16000).detected is False
    clock.advance(2.0)
    assert manager.process_audio_chunk(frame(), 16000).detected is True
