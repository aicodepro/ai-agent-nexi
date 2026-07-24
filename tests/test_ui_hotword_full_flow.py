import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_hotword_full_ui_flow():
    from engine.ui_state_manager import UIStateManager
    mgr = UIStateManager(dedupe_ms=0)
    flow = [
        mgr.emit("sleep", source="system"),
        mgr.emit("wake_detected", source="hotword"),
        mgr.emit("listening", source="hotword"),
        mgr.emit("recognising", source="asr"),
        mgr.emit("thinking", source="assistant"),
        mgr.emit("saying", source="tts"),
        mgr.emit("sleep", source="system"),
    ]
    assert [e.state for e in flow if e] == ["sleep", "online", "listening", "recognising", "thinking", "saying", "sleep"]
    assert flow[1].log_message == "WAKE: Hotword detected"
