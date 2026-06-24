import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import UIStateManager


def test_online_followed_by_listening_followed_by_recognising():
    mgr = UIStateManager(dedupe_ms=0)
    e1 = mgr.online(source="hotword")
    e2 = mgr.listening(source="hotword")
    e3 = mgr.recognising(source="hotword")
    assert e1.state == "online"
    assert e2.state == "listening"
    assert e3.state == "recognising"
