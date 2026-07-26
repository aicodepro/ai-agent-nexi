"""A typed request is still a NEXI turn and must be able to hear the answer.

Live trace - every UI turn carried an empty session:
    [UI_SEND] state=saying label=SAYING source=tts session= sequence=1

post_followup_capture() bailed on `not session_id`, and
current_bridge_session_id() is a voice-session threadlocal that is empty for
typed input. So NEXI asked "What should I name the folder?" and could never open
the microphone for the reply - the question was a dead end by construction.

Adding "ui" to _FOLLOWUP_SOURCES got the request further but not past this.
"""
from __future__ import annotations

import queue
from unittest.mock import patch

import pytest

from engine import runtime_bridge


def test_typed_request_still_queues_a_capture():
    """No voice session exists, so the capture must ask for one to be created."""
    q = queue.Queue()
    assert runtime_bridge.post_followup_capture(
        q, "", source="ui", reason="missing_slot") is True, \
        "a typed request could not request the microphone"

    event = q.get_nowait()
    assert event["type"] == runtime_bridge.CONTROL_CAPTURE_FOLLOWUP
    assert event["start_session"] is True
    assert event["source"] == "ui"


def test_voice_request_does_not_ask_for_a_new_session():
    """An existing voice session must be joined, never replaced."""
    q = queue.Queue()
    assert runtime_bridge.post_followup_capture(
        q, "sess-live", source="hotword", reason="missing_slot") is True

    event = q.get_nowait()
    assert event["session_id"] == "sess-live"
    assert event["start_session"] is False


def test_no_control_queue_is_still_a_failure():
    assert runtime_bridge.post_followup_capture(
        None, "", source="ui", reason="missing_slot") is False


def test_capture_starts_a_session_when_typed():
    """The audio-process side: a start_session capture creates a real session."""
    from engine.audio_wake_pipeline import AudioWakePipeline

    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline.start_session", return_value="sess-new") as start:
        msm.return_value.is_current.return_value = True
        msm.return_value.set_state.return_value = None
        p = AudioWakePipeline(command_queue=queue.Queue())
        # capture_command is the blocking part; stub it out - this test is about
        # whether a session gets created at all.
        with patch.object(p, "capture_command", return_value=b""), \
             patch.object(p, "flush_wake_tail"), \
             patch.object(p, "_post_status"), \
             patch("engine.audio_wake_pipeline.finish_session"):
            p._capture_followup({
                "type": "capture_followup", "session_id": "",
                "start_session": True, "source": "ui",
                "reason": "missing_slot", "not_before": 0.0,
            })

    start.assert_called_once_with("ui")


def test_capture_without_start_flag_is_still_rejected():
    """A sessionless capture that did NOT ask for a session stays rejected."""
    from engine.audio_wake_pipeline import AudioWakePipeline

    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline.start_session") as start:
        msm.return_value.is_current.return_value = False
        p = AudioWakePipeline(command_queue=queue.Queue())
        handled = p._capture_followup({
            "type": "capture_followup", "session_id": "",
            "source": "ui", "reason": "missing_slot", "not_before": 0.0,
        })

    assert handled is False
    start.assert_not_called()
