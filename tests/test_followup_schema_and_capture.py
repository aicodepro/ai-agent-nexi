"""Schema validation, durable capture state, and switch/cancel ownership.

B2-2: a pending question accepted whatever arrived next.
B2-4: the auto-listen request was consumed when it was ASKED FOR, not when the
      microphone actually opened, so a capture that never started vanished with
      nothing recording it.
B2-5: switching or cancelling cleared the legacy store but left the new
      DialogueContext open, which would recreate the ownership bug.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from engine import followup_manager as fm, dialogue_context as dc
from engine.dialogue_context import CaptureState, DialogueStatus


@pytest.fixture(autouse=True)
def _reset():
    fm.clear_followup("test-setup")
    dc.reset_for_tests()
    yield
    fm.clear_followup("test-teardown")
    dc.reset_for_tests()


def _no_session():
    return patch("engine.runtime_bridge.current_bridge_session_id", return_value="")


# --- B2-2: typed answers -----------------------------------------------------

def test_a_command_does_not_satisfy_a_folder_name_question():
    """The live failure: "show me your diagnostics" stored as a folder name."""
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        result = fm.consume_followup_answer("show me your diagnostics", source="ui")

    assert result.get("reprompt") is True, "a command was accepted as the folder name"
    assert result["route"] == "clarify"
    assert fm.has_pending_followup() is True, "the question was dropped instead of re-asked"


def test_a_real_answer_is_accepted():
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        result = fm.consume_followup_answer("Project Alpha", source="ui")

    assert result["handled"] is True
    assert result.get("reprompt") is not True
    assert result["answer"] == "Project Alpha"
    assert fm.has_pending_followup() is False


def test_repeated_bad_answers_stop_re_asking():
    """Re-asking forever is its own failure mode."""
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        # "con" is a Windows-reserved name: invalid, but NOT a switch phrase,
        # so it reaches schema validation rather than being routed away.
        for _ in range(fm._MAX_SCHEMA_RETRIES):
            assert fm.consume_followup_answer("con", source="ui").get("reprompt") is True
        final = fm.consume_followup_answer("con", source="ui")

    assert final.get("reprompt") is not True
    assert final["handled"] is False
    assert fm.has_pending_followup() is False


def test_a_reprompt_asks_for_the_right_kind_of_thing():
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        result = fm.consume_followup_answer("con", source="ui")

    assert "call the folder" in result["text"].lower()


# --- B2-5: switch and cancel close the dialogue too --------------------------

def test_cancel_closes_the_dialogue():
    dc.open_dialogue(question="What should I name the folder?", workflow_id="create_folder")
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        result = fm.consume_followup_answer("never mind", source="ui")

    assert result["cancelled"] is True
    assert dc.get_active(None) is None, "the dialogue survived a cancel"


def test_switching_closes_the_dialogue():
    dc.open_dialogue(question="What should I name the folder?", workflow_id="create_folder")
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        result = fm.consume_followup_answer("open chrome", source="ui")

    assert result["route"] == "switch"
    assert dc.get_active(None) is None, "the dialogue survived a workflow switch"


def test_consuming_a_good_answer_closes_the_dialogue():
    dc.open_dialogue(question="What should I name the folder?", workflow_id="create_folder")
    with _no_session():
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        fm.consume_followup_answer("Project Alpha", source="ui")

    assert dc.get_active(None) is None


# --- B2-4: the capture request is durable ------------------------------------

def test_the_request_survives_until_the_microphone_really_opens():
    dc.open_dialogue(question="What should I name it?", session_id="sess-A")

    dc.set_capture_state(CaptureState.REQUESTED)
    assert dc.capture_is_pending() is True
    dc.set_capture_state(CaptureState.QUEUED)
    assert dc.capture_is_pending() is True, "the request was dropped before capture started"

    dc.set_capture_state(CaptureState.CAPTURE_STARTED)
    assert dc.capture_is_pending() is True
    dc.set_capture_state(CaptureState.COMPLETED)
    assert dc.capture_is_pending() is False


def test_a_capture_that_never_starts_stays_outstanding():
    """The point of B2-4: nothing silently forgets an unfulfilled request."""
    dc.open_dialogue(question="What should I name it?", session_id="sess-A")
    dc.set_capture_state(CaptureState.QUEUED)
    assert dc.capture_is_pending() is True


def test_no_speech_closes_the_capture_without_an_answer():
    dc.open_dialogue(question="What should I name it?", session_id="sess-A")
    dc.set_capture_state(CaptureState.QUEUED)
    dc.set_capture_state(CaptureState.NO_SPEECH)
    assert dc.capture_is_pending() is False
