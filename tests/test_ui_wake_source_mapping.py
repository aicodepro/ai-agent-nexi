import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_double_clap_wake_maps_to_mark_ui_state():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateNexiState", create=True) as update:
        handle_bridge_event({"type": "status", "status": "wake_detected", "source": "double_clap"})
    payload = update.call_args[0][0]
    assert payload["state"] == "online"
    assert payload["label"] == "ONLINE"
    assert payload["source"] == "double_clap"


def test_empty_asr_result_logs_no_speech_message():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.appendLog", create=True) as append_log, patch("eel.updateNexiState", create=True):
        handle_bridge_event({"type": "status", "status": "asr_result", "source": "hotword", "text": ""})
    assert append_log.call_args[0][1] == "SYS: No speech detected. Please try again."
