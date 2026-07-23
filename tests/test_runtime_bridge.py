import os
import sys
import time
import multiprocessing

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock

import pytest

from engine.runtime_bridge import (
    BridgeEvent,
    post_command,
    post_status,
    post_wake_detected,
    post_asr_started,
    post_asr_result,
    post_error,
    handle_bridge_event,
    EVENT_COMMAND_TEXT,
    EVENT_STATUS,
    EVENT_WAKE_DETECTED,
    EVENT_ASR_STARTED,
    EVENT_ASR_RESULT,
    EVENT_SLEEPING,
    EVENT_ERROR,
)


@pytest.fixture
def q():
    return multiprocessing.Queue()


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

def test_post_command_puts_pickle_safe_event(q):
    ok = post_command(q, "what is 2+2", source="hotword")
    assert ok is True
    event = q.get_nowait()
    assert isinstance(event, dict)
    assert event["type"] == EVENT_COMMAND_TEXT
    assert event["text"] == "what is 2+2"
    assert event["source"] == "hotword"
    assert "created_at" in event


def test_bridge_event_to_dict_is_pickle_safe():
    event = BridgeEvent(type=EVENT_STATUS, status="listening", source="test").to_dict()
    assert isinstance(event, dict)
    assert event["type"] == EVENT_STATUS
    assert event["created_at"] > 0


def test_post_command_rejects_empty_text(q):
    assert post_command(q, "", source="hotword") is False
    assert post_command(q, "   ", source="hotword") is False
    assert post_command(q, None, source="hotword") is False


def test_post_command_rejects_none_queue():
    assert post_command(None, "hello", source="hotword") is False


def test_post_status_puts_event(q):
    ok = post_status(q, "listening", source="clap", text="preview")
    assert ok is True
    event = q.get_nowait()
    assert event["type"] == EVENT_STATUS
    assert event["status"] == "listening"
    assert event["text"] == "preview"


def test_followup_capture_is_scheduled_after_cooldown_with_boundary_margin(q):
    from engine.runtime_bridge import request_followup_capture

    with patch("engine.runtime_bridge.current_bridge_session_id", return_value="sess-followup"), patch(
        "engine.runtime_bridge._control_queue", q
    ), patch("engine.post_tts_cleanup.get_cooldown_remaining_ms", return_value=800):
        assert request_followup_capture(source="hotword", reason="missing_slot") is True

    event = q.get(timeout=1)
    assert event["type"] == "capture_followup"
    assert event["session_id"] == "sess-followup"
    assert event["not_before"] - event["created_at"] >= 0.84


def test_post_error_puts_event(q):
    ok = post_error(q, "mic failed", source="audio")
    assert ok is True
    event = q.get_nowait()
    assert event["type"] == EVENT_ERROR
    assert event["error"] == "mic failed"


def test_required_runtime_event_types_do_not_call_allCommands(q):
    assert post_wake_detected(q, source="hotword") is True
    assert post_asr_started(q, source="hotword") is True
    assert post_asr_result(q, "hello", source="hotword") is True
    events = [q.get(timeout=1), q.get(timeout=1), q.get(timeout=1)]
    assert [event["type"] for event in events] == [
        EVENT_WAKE_DETECTED,
        EVENT_ASR_STARTED,
        EVENT_ASR_RESULT,
    ]
    with patch("engine.command.allCommands") as mock_all:
        for event in events:
            handle_bridge_event(event)
        mock_all.assert_not_called()


# ---------------------------------------------------------------------------
# Consuming
# ---------------------------------------------------------------------------

def test_ui_bridge_pump_calls_allCommands_once():
    """handle_bridge_event dispatches a command_text event to allCommands."""
    event = {"type": EVENT_COMMAND_TEXT, "text": "what is 2+2", "source": "hotword"}
    with patch("engine.command.allCommands") as mock_all:
        handle_bridge_event(event)
        mock_all.assert_called_once_with("what is 2+2")


def test_bridge_post_receive_dispatch_once(q):
    assert post_command(q, "hello", source="clap") is True
    event = q.get(timeout=1)
    with patch("engine.command.allCommands") as mock_all:
        handle_bridge_event(event)
        mock_all.assert_called_once_with("hello")


def test_status_event_does_not_call_allCommands():
    event = {"type": EVENT_STATUS, "status": "listening", "source": "clap"}
    with patch("engine.command.allCommands") as mock_all:
        handle_bridge_event(event)
        mock_all.assert_not_called()


def test_sleeping_status_updates_ui_state():
    event = {"type": EVENT_STATUS, "status": EVENT_SLEEPING, "source": "system"}
    with patch("eel.updateNexiState", create=True) as mock_update:
        handle_bridge_event(event)
    payload = mock_update.call_args[0][0]
    assert payload.get("state") == "sleep"
    assert payload.get("status") == "sleeping"


def test_error_event_does_not_crash():
    event = {"type": EVENT_ERROR, "error": "mic exploded", "source": "audio"}
    # Must not raise.
    handle_bridge_event(event)


def test_empty_text_command_event_is_ignored():
    event = {"type": EVENT_COMMAND_TEXT, "text": "", "source": "hotword"}
    with patch("engine.command.allCommands") as mock_all:
        handle_bridge_event(event)
        mock_all.assert_not_called()


def test_bridge_event_preview_does_not_contain_full_long_text(capsys):
    long_text = "a" * 200
    event = {"type": EVENT_COMMAND_TEXT, "text": long_text, "source": "test"}
    with patch("engine.command.allCommands"):
        handle_bridge_event(event)
    out = capsys.readouterr().out
    # The log line should exist but not contain the full 200-char string.
    assert "a" * 200 not in out
    assert "chars=200" in out


def test_pending_followup_waits_for_audio_process_listening_event():
    event = {
        "type": EVENT_COMMAND_TEXT,
        "text": "create a folder",
        "source": "hotword",
        "session_id": "sess-followup",
    }

    with patch("engine.command_bus.submit_user_command", return_value=True), patch(
        "engine.followup_manager.has_pending_followup", return_value=True
    ), patch(
        "engine.clarification_manager.has_pending_clarification", return_value=False
    ), patch("engine.runtime_bridge._set_ui_state") as set_state, patch(
        "engine.runtime_bridge._finish_session"
    ) as finish:
        handle_bridge_event(event)

    assert not any(call.args[0] == "listening" for call in set_state.call_args_list)
    finish.assert_not_called()


def test_command_dispatch_propagates_session_to_tts_ui_state():
    import engine.command as command
    from engine.runtime_bridge import current_bridge_session_id

    seen = []

    def submit(*_args, **_kwargs):
        seen.append(current_bridge_session_id())
        command._set_ui_state("saying", source="tts")
        return True

    event = {
        "type": EVENT_COMMAND_TEXT,
        "text": "what is 2+2",
        "source": "hotword",
        "session_id": "sess123",
    }
    with patch("engine.command_bus.submit_user_command", side_effect=submit), patch(
        "eel.updateNexiState", create=True
    ) as update:
        handle_bridge_event(event)

    saying = [call.args[0] for call in update.call_args_list if call.args[0]["state"] == "saying"]
    assert seen == ["sess123"]
    assert saying and saying[-1]["session_id"] == "sess123"


def test_empty_asr_result_finishes_session_once():
    event = {"type": EVENT_ASR_RESULT, "text": "", "source": "hotword", "session_id": "sess-empty"}

    with patch("engine.wake_session_manager.ignore_if_stale", return_value=False), patch(
        "engine.runtime_bridge._finish_session"
    ) as finish:
        handle_bridge_event(event)

    finish.assert_called_once_with("sess-empty")


def test_empty_asr_status_finishes_session_once():
    event = {
        "type": EVENT_STATUS,
        "status": EVENT_ASR_RESULT,
        "text": "",
        "source": "hotword",
        "session_id": "sess-empty-status",
    }

    with patch("engine.wake_session_manager.ignore_if_stale", return_value=False), patch(
        "engine.runtime_bridge._finish_session"
    ) as finish:
        handle_bridge_event(event)

    finish.assert_called_once_with("sess-empty-status")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
