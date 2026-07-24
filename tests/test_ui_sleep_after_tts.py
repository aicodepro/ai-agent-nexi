import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tts_done_returns_sleep():
    from engine.ui_state_manager import UIStateManager
    mgr = UIStateManager(dedupe_ms=0)
    mgr.emit("saying", source="tts")
    done = mgr.emit("tts_done", source="tts")
    assert done.state == "sleep"
    assert done.label == "SLEEPING"
