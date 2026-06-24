import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_saying_state_during_tts_aliases():
    from engine.ui_state_manager import UIStateManager
    mgr = UIStateManager(dedupe_ms=0)
    event = mgr.emit("speaking", source="tts")
    assert event.state == "saying"
    assert event.label == "SAYING"
    assert event.log_message == "SYS: Saying..."
