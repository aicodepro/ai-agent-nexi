from __future__ import annotations

from unittest.mock import patch


def _states(update):
    return [call.args[0]["state"] for call in update.call_args_list]


def test_tts_saying_then_sleeping():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateJarvisState", create=True) as update:
        handle_bridge_event({"type": "status", "status": "speaking_started", "source": "tts"})
        handle_bridge_event({"type": "status", "status": "sleeping", "source": "ready"})

    assert _states(update) == ["saying", "sleep"]

