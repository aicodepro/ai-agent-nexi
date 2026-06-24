import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.runtime_bridge import EVENT_STATUS, handle_bridge_event


def _ui_payloads(mock_update):
    payloads = []
    for call in mock_update.call_args_list:
        raw = call.args[0]
        payloads.append(raw)
    return payloads


def test_wake_detected_only_one_state_emit():
    event = {"type": EVENT_STATUS, "status": "wake_detected", "source": "hotword"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert len(payloads) == 1
    assert payloads[0]["state"] == "online"
    assert payloads[0]["message"] == "ONLINE"


def test_listening_only_one_state_emit():
    event = {"type": EVENT_STATUS, "status": "listening", "source": "hotword"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert len(payloads) == 1
    assert payloads[0]["state"] == "listening"
    assert payloads[0]["message"] == "LISTENING"


def test_wake_detected_does_not_emit_hotword_detected():
    event = {"type": EVENT_STATUS, "status": "wake_detected", "source": "hotword"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert all(p["message"] != "HOTWORD DETECTED" for p in payloads)


def test_wake_detected_does_not_emit_double_clap_detected():
    event = {"type": EVENT_STATUS, "status": "wake_detected", "source": "double_clap"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert all(p["message"] != "DOUBLE CLAP DETECTED" for p in payloads)
