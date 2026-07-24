import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import canonical_state, label_for


def test_speech_started_canonical_is_recognising():
    assert canonical_state("speech_started") == "recognising"


def test_speech_started_label_is_recognising():
    assert label_for("speech_started") == "RECOGNISING"


def test_asr_started_canonical_is_recognising():
    assert canonical_state("asr_started") == "recognising"


def test_asr_started_label_is_recognising():
    assert label_for("asr_started") == "RECOGNISING"


def test_runtime_bridge_maps_speech_started_to_recognising():
    from engine.runtime_bridge import STATUS_TO_UI_STATE
    assert STATUS_TO_UI_STATE.get("speech_started") == "recognising"


def test_runtime_bridge_maps_asr_started_to_recognising():
    from engine.runtime_bridge import STATUS_TO_UI_STATE
    assert STATUS_TO_UI_STATE.get("asr_started") == "recognising"


def test_runtime_bridge_maps_wake_detected_to_online():
    from engine.runtime_bridge import STATUS_TO_UI_STATE
    assert STATUS_TO_UI_STATE.get("wake_detected") == "online"
