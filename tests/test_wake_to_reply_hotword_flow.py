import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import emit_state, get_ui_state_manager, UIStateManager, canonical_state, label_for, log_for


def test_wake_to_reply_state_sequence():
    manager = UIStateManager(dedupe_ms=0)
    sequence = ["wake_detected", "listening", "waiting_for_speech", "recognising", "thinking", "saying", "sleep"]
    for i, state in enumerate(sequence):
        event = manager.emit(state, source="hotword" if state == "wake_detected" else "system")
        assert event is not None
        assert event.state == canonical_state(state)


def test_hotword_detected_has_correct_label():
    event = emit_state("wake_detected", source="hotword", force=True)
    assert event is not None
    assert event.label == "ONLINE"


def test_listening_has_correct_label():
    event = emit_state("listening", source="system", force=True)
    assert event is not None
    assert event.label == "LISTENING"


def test_thinking_has_correct_label():
    event = emit_state("thinking", source="system", force=True)
    assert event is not None
    assert event.label == "THINKING"


def test_no_duplicate_state_short_window():
    manager = UIStateManager(dedupe_ms=500)
    e1 = manager.emit("thinking", source="system", force=True)
    e2 = manager.emit("thinking", source="system")
    assert e1 is not None
    assert e2 is None
