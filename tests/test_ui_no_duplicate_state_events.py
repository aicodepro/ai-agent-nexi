import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_ui_dedupes_same_state_within_window():
    from engine.ui_state_manager import UIStateManager

    mgr = UIStateManager(dedupe_ms=250)
    first = mgr.emit("listening", source="hotword")
    second = mgr.emit("listening", source="hotword")
    assert first is not None
    assert second is None
    assert len(mgr.events) == 1
