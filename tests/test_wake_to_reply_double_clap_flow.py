import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import emit_state, UIStateManager, canonical_state


def test_double_clap_detected_label():
    event = emit_state("wake_detected", source="double_clap", force=True)
    assert event is not None
    assert event.label == "ONLINE"
    assert event.log_message == "WAKE: Double clap detected"


def test_double_clap_full_flow():
    manager = UIStateManager(dedupe_ms=0)
    sequence = [
        ("wake_detected", "double_clap"),
        ("listening", "system"),
        ("waiting_for_speech", "system"),
        ("recognising", "system"),
        ("thinking", "system"),
        ("saying", "system"),
        ("sleep", "system"),
    ]
    for state, source in sequence:
        event = manager.emit(state, source=source)
        assert event is not None
        assert event.state == canonical_state(state)


def test_double_clap_to_sleep_no_gaps():
    manager = UIStateManager(dedupe_ms=0)
    states = []
    for s, src in [("wake_detected", "double_clap"), ("listening", "system"),
                    ("waiting_for_speech", "system"), ("recognising", "system"),
                    ("thinking", "system"), ("saying", "system"), ("sleep", "system")]:
        e = manager.emit(s, source=src)
        if e:
            states.append(e.state)
    assert states == ["online", "listening", "waiting_for_speech",
                       "recognising", "thinking", "saying", "sleep"]
