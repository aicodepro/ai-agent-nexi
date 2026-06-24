import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_zero_signal_does_not_crash():
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"scorer": lambda audio: 0.0, "enforce_rms_gate": True})
    result = manager.process_audio_chunk(b"\x00\x00" * 1280, 16000)
    assert result.detected is False
    assert result.score == 0.0
