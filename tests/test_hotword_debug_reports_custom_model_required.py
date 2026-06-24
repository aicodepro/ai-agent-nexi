import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_custom_hotword_required_after_low_scores():
    from engine.hotword_engine_manager import HotwordEngineManager

    frame = struct.pack("<1280h", *([900] * 1280))
    manager = HotwordEngineManager({"scorer": lambda audio: 0.01, "threshold": 0.25})
    for _ in range(5):
        manager.process_audio_chunk(frame, 16000)
    status = manager.get_status()
    assert status["max_score"] < 0.05
    assert status["custom_hotword_required"] is True
