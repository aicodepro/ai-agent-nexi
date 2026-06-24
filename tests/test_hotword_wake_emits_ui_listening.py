import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.hotword_engine_manager import HotwordEngineManager, HotwordResult


def test_hotword_result_structure():
    result = HotwordResult(
        detected=True,
        engine="openwakeword",
        phrase="hey jarvis",
        score=0.8,
        threshold=0.25,
        latency_ms=50.0,
        reason="detected",
    )
    assert result.detected is True
    assert result.engine == "openwakeword"
    assert result.phrase == "hey jarvis"


def test_hotword_below_threshold_no_detect():
    engine = HotwordEngineManager(config={"enabled": False})
    result = engine._result(False, 0.1, time.time(), "below_threshold")
    assert result.detected is False
    assert result.reason == "below_threshold"


def test_hotword_detection_uses_threshold():
    engine = HotwordEngineManager(config={"enabled": False})
    engine.threshold = 0.25
    engine.consecutive_hits_required = 1
    engine.cooldown_ms = 0
    engine._prev_score = 0.0
    result = engine.process_audio_chunk(b"\x00\x01" * 640, 16000)
    assert result.detected is False  # score is near zero since no real model
