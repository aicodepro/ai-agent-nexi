import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_hotword_manager_rejects_wrong_sample_rate():
    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"scorer": lambda audio: 1.0, "sample_rate": 16000})
    result = manager.process_audio_chunk(b"\x00\x00" * 1280, sample_rate=8000)
    assert result.detected is False
    assert "sample_rate_mismatch" in result.reason


def test_hotword_manager_uses_int16_pcm_bytes():
    from engine.hotword_engine_manager import HotwordEngineManager

    seen = {}

    def scorer(audio):
        seen["length"] = len(audio)
        seen["first"] = struct.unpack("<h", audio[:2])[0]
        return 0.9

    frame = struct.pack("<1280h", *([123] * 1280))
    manager = HotwordEngineManager({"scorer": scorer, "threshold": 0.5, "sample_rate": 16000})
    result = manager.process_audio_chunk(frame, sample_rate=16000)
    assert result.detected is True
    assert seen == {"length": 2560, "first": 123}


def test_openwakeword_name_normalisation_prefers_spaces():
    from engine.hotword_engine_manager import _normalise_oww_name

    assert _normalise_oww_name("hey_nexi") == "hey nexi"
    assert _normalise_oww_name("Hey Nexi") == "hey nexi"
