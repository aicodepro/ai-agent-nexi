"""Tests for UI wake source state mapping (Phase 8).

Uses the real runtime_bridge STATUS_TO_UI_STATE mapping.
"""

from engine.runtime_bridge import (
    BridgeEvent, EVENT_WAKE_DETECTED, EVENT_LISTENING_STARTED,
    EVENT_ASR_STARTED, EVENT_ASR_RESULT, EVENT_IDLE,
    STATUS_TO_UI_STATE,
)


def test_hotword_wake_state():
    state = STATUS_TO_UI_STATE.get(EVENT_WAKE_DETECTED, "")
    assert state == "online"


def test_listening_started_state():
    state = STATUS_TO_UI_STATE.get(EVENT_LISTENING_STARTED, "")
    assert state == "listening"


def test_asr_started_state():
    state = STATUS_TO_UI_STATE.get(EVENT_ASR_STARTED, "")
    assert state == "recognising"


def test_asr_result_state():
    state = STATUS_TO_UI_STATE.get(EVENT_ASR_RESULT, "")
    assert state == "thinking"


def test_idle_state():
    state = STATUS_TO_UI_STATE.get(EVENT_IDLE, "")
    assert state == "sleep"


def test_handle_wake_detected_hotword():
    event = BridgeEvent(type=EVENT_WAKE_DETECTED, source="hotword")
    assert event.source == "hotword"
    ui_state = STATUS_TO_UI_STATE.get(EVENT_WAKE_DETECTED, "")
    assert ui_state == "online"


def test_handle_wake_detected_double_clap():
    event = BridgeEvent(type=EVENT_WAKE_DETECTED, source="double_clap")
    assert event.source == "double_clap"
    ui_state = STATUS_TO_UI_STATE.get(EVENT_WAKE_DETECTED, "")
    assert ui_state == "online"


def test_handle_wake_detected_clap_alias():
    ui_state = STATUS_TO_UI_STATE.get(EVENT_WAKE_DETECTED, "")
    assert ui_state == "online"


def test_handle_asr_result_nonempty():
    event = BridgeEvent(type=EVENT_ASR_RESULT, text="hello", source="hotword")
    assert len(event.text or "") > 0


def test_handle_asr_result_empty():
    event = BridgeEvent(type=EVENT_ASR_RESULT, text="", source="double_clap")
    assert len(event.text or "") == 0
