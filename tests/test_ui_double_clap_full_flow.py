import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_double_clap_full_ui_flow():
    from engine.ui_state_manager import UIStateManager
    mgr = UIStateManager(dedupe_ms=0)
    wake = mgr.emit("wake_detected", source="double_clap")
    listen = mgr.emit("listening", source="double_clap")
    assert wake.label == "ONLINE"
    assert wake.log_message == "WAKE: Double clap detected"
    assert listen.state == "listening"
