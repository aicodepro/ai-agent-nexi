import os
import sys
import json
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import UIStateManager, canonical_state


def test_empty_asr_sets_sleep():
    manager = UIStateManager(dedupe_ms=0)
    event = manager.emit("sleep", source="hotword", status="asr_result")
    assert event is not None
    assert event.state == "sleep"


def test_asr_empty_results_in_sleep_state():
    manager = UIStateManager(dedupe_ms=0)
    e1 = manager.emit("recognising", source="hotword", force=True)
    e2 = manager.emit("sleep", source="hotword", status="asr_empty", force=True)
    assert e2 is not None
    assert e2.state == "sleep"


def test_asr_resets_to_sleep_after_empty():
    manager = UIStateManager(dedupe_ms=0)
    events = []
    for state, src in [("wake_detected", "hotword"), ("listening", "system"),
                        ("waiting_for_speech", "system"),
                        ("recognising", "system"), ("sleep", "system")]:
        e = manager.emit(state, source=src)
        if e:
            events.append(e.state)
    assert events[-1] == "sleep"
