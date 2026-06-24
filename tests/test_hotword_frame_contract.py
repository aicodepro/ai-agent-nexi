import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_hotword_frame_contract_defaults(monkeypatch):
    monkeypatch.delenv("JARVIS_WAKE_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("JARVIS_WAKE_FRAME_MS", raising=False)
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"scorer": lambda audio: 0.0})
    status = manager.get_status()
    assert status["sample_rate"] == 16000
    assert status["frame_ms"] == 80


def test_hotword_accepts_80ms_pcm16_frame_with_realistic_rms():
    from engine.hotword_engine_manager import HotwordEngineManager

    frame = struct.pack("<1280h", *([900] * 1280))
    manager = HotwordEngineManager({
        "scorer": lambda audio: 0.9,
        "threshold": 0.25,
        "min_rms": 0.004,
        "enforce_rms_gate": True,
    })
    result = manager.process_audio_chunk(frame, 16000)
    assert result.detected is True
    assert result.reason == "detected"
