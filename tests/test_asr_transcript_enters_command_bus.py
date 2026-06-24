from __future__ import annotations

from unittest.mock import patch


def test_asr_transcript_enters_command_bus():
    from engine.runtime_bridge import handle_bridge_event

    with patch("eel.updateJarvisState", create=True), patch("engine.command_bus.submit_user_command", return_value=True) as submit:
        handle_bridge_event({"type": "command_text", "source": "hotword", "text": "what time is it"})

    submit.assert_called_once()
    args, kwargs = submit.call_args
    assert args[0] == "what time is it"
    assert kwargs["source"] == "hotword"
    assert kwargs["mode"] == "voice"

