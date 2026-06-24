import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_no_speech_returns_sleep_state():
    from engine.ui_state_manager import UIStateManager
    mgr = UIStateManager(dedupe_ms=0)
    mgr.emit("waiting_for_speech", source="hotword")
    event = mgr.emit("sleep", source="hotword", status="no_speech")
    assert event.state == "sleep"
