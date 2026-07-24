import os
import sys
import json
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import UIStateManager, canonical_state


def test_tts_sets_saying():
    manager = UIStateManager(dedupe_ms=0)
    event = manager.emit("saying", source="tts", force=True)
    assert event is not None
    assert event.state == "saying"


def test_sleep_after_tts():
    manager = UIStateManager(dedupe_ms=0)
    e1 = manager.emit("saying", source="tts", force=True)
    e2 = manager.emit("sleep", source="tts", force=True)
    assert e2.state == "sleep"


def test_saying_to_sleep_sequence():
    manager = UIStateManager(dedupe_ms=0)
    events = []
    for s in ["saying", "sleep"]:
        e = manager.emit(s, source="tts", force=True)
        if e:
            events.append(e.state)
    assert events == ["saying", "sleep"]
