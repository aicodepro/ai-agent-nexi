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


def test_waiting_for_speech_shows_listening():
    event = {"type": EVENT_STATUS, "status": "waiting_for_speech", "source": "hotword"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert payloads[0]["state"] == "waiting_for_speech"
    assert payloads[0]["message"] == "LISTENING"


def test_speech_started_shows_recognising():
    event = {"type": EVENT_STATUS, "status": "speech_started", "source": "hotword"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert payloads[0]["state"] == "recognising"
    assert payloads[0]["message"] == "RECOGNISING"


def test_speech_started_not_listening():
    event = {"type": EVENT_STATUS, "status": "speech_started", "source": "hotword"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert all(p["state"] != "listening" for p in payloads)
