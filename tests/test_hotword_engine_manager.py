import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class Scores:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def score(self, audio_chunk):
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


def test_hotword_manager_detects_threshold_hit():
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"scorer": Scores([0.4]), "threshold": 0.35, "consecutive_hits": 1, "sample_rate": 16000})
    result = manager.process_audio_chunk(b"\x00\x00" * 1280, 16000)
    assert result.detected is True
    assert result.engine == "openwakeword"
    assert result.phrase == "hey nexi"


def test_hotword_manager_respects_cooldown():
    from engine.hotword_engine_manager import HotwordEngineManager

    clock = FakeClock()
    manager = HotwordEngineManager({"scorer": Scores([0.5, 0.5, 0.9]), "threshold": 0.35, "cooldown_ms": 1500, "clock": clock})
    assert manager.process_audio_chunk(b"\x00\x00" * 1280, 16000).detected is True
    assert manager.process_audio_chunk(b"\x00\x00" * 1280, 16000).detected is False
    clock.advance(2.0)
    assert manager.process_audio_chunk(b"\x00\x00" * 1280, 16000).detected is True


def test_hotword_manager_rejects_wrong_sample_rate():
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"scorer": Scores([0.9]), "sample_rate": 16000})
    result = manager.process_audio_chunk(b"\x00\x00" * 1280, 8000)
    assert result.detected is False
    assert "sample_rate_mismatch" in result.reason
