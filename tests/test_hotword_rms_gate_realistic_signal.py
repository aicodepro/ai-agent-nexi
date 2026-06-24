import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_rms_gate_allows_realistic_voice_like_signal():
    from engine.hotword_engine_manager import HotwordEngineManager

    frame = struct.pack("<1280h", *([700, -700] * 640))
    manager = HotwordEngineManager({
        "scorer": lambda audio: 0.7,
        "threshold": 0.25,
        "min_rms": 0.004,
        "enforce_rms_gate": True,
    })
    result = manager.process_audio_chunk(frame, 16000)
    assert result.detected is True


def test_rms_gate_rejects_true_zero_signal_when_enforced():
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({
        "scorer": lambda audio: 0.9,
        "threshold": 0.25,
        "min_rms": 0.004,
        "enforce_rms_gate": True,
    })
    result = manager.process_audio_chunk(b"\x00\x00" * 1280, 16000)
    assert result.detected is False
    assert result.reason.startswith("low_rms_")
