import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _payloads(mock_update):
    return [call.args[0] for call in mock_update.call_args_list]


def test_hotword_status_maps_to_online():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateJarvisState", create=True) as update:
        handle_bridge_event({"type": "status", "status": "wake_detected", "source": "hotword"})
    assert _payloads(update)[0]["state"] == "online"
    assert _payloads(update)[0]["label"] == "ONLINE"


def test_clap_status_maps_to_online():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateJarvisState", create=True) as update:
        handle_bridge_event({"type": "status", "status": "wake_detected", "source": "clap"})
    assert _payloads(update)[0]["state"] == "online"
    assert _payloads(update)[0]["label"] == "ONLINE"


def test_asr_result_posts_transcript_and_thinking():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateJarvisState", create=True) as update, patch("eel.senderText", create=True) as sender:
        handle_bridge_event({"type": "status", "status": "asr_result", "source": "hotword", "text": "what is AI"})
    states = [payload["state"] for payload in _payloads(update)]
    assert states == ["recognising", "thinking"]
    sender.assert_called_once_with("what is AI")


def test_empty_asr_result_logs_warning_and_sleep():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateJarvisState", create=True) as update, patch("eel.appendLog", create=True) as log:
        handle_bridge_event({"type": "status", "status": "asr_result", "source": "hotword", "text": ""})
    assert _payloads(update)[-1]["state"] == "sleep"
    assert log.called
