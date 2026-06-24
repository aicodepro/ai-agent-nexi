import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeModel:
    def predict(self, samples):
        return {"noise": 0.1, "hey_nexi": 0.82, "nexi": 0.4}


def test_hotword_prediction_key_matches_configured_phrase():
    from engine.hotword_engine_manager import HotwordEngineManager

    frame = struct.pack("<1280h", *([1000] * 1280))
    manager = HotwordEngineManager({"enabled": False, "threshold": 0.25, "phrases": "hey nexi,nexi"})
    manager.enabled = True
    manager._model = FakeModel()
    manager._configured_names = ["hey nexi", "nexi"]
    result = manager.process_audio_chunk(frame, 16000)
    status = manager.get_status()
    assert result.detected is True
    assert status["selected_key"] == "hey_nexi"
    assert "hey_nexi" in status["prediction_keys"]
