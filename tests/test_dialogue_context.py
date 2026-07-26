"""DialogueContext: session ownership, durable capture, field collection.

The defect this module exists for, from a real session:

    [UI]      create a folder     -> pending folder_name, no session recorded
    ... that session ends ...
    [hotword] "Create a folder"   -> consumed as the ANSWER to the old question
    [WORKFLOW] slot_saved name=folder_name

followup_manager._pending and workflow_state._workflow are process-global with
no session or turn binding, so a question raised in one session was visible -
and answerable - in the next.
"""
from __future__ import annotations

import time

import pytest

from engine import dialogue_context as dc
from engine.dialogue_context import CaptureState, DialogueStatus


@pytest.fixture(autouse=True)
def _reset():
    dc.reset_for_tests()
    yield
    dc.reset_for_tests()


# --- session ownership: the reason this module exists ------------------------

def test_a_question_is_invisible_to_a_different_session():
    dc.open_dialogue(question="What should I name the folder?",
                     session_id="sess-A", workflow_id="create_folder",
                     required_fields=["folder_name"])

    assert dc.get_active("sess-A") is not None
    assert dc.get_active("sess-B") is None, "a new session inherited the old question"


def test_a_foreign_session_cannot_answer():
    dc.open_dialogue(question="What should I name it?", session_id="sess-A",
                     workflow_id="create_folder", required_fields=["folder_name"])

    assert dc.collect_field("folder_name", "Create a folder", session_id="sess-B") is None, \
        "a different session answered the previous session's question"
    assert dc.get_active("sess-A").collected_fields == {}


def test_finishing_the_owning_session_drops_the_question():
    dc.open_dialogue(question="What should I name it?", session_id="sess-A",
                     workflow_id="create_folder")
    dc.on_session_finished("sess-A")
    assert dc.get_active("sess-A") is None
    assert dc.get_active(None) is None, "the question outlived its session"


def test_finishing_an_unrelated_session_leaves_it_alone():
    dc.open_dialogue(question="What should I name it?", session_id="sess-A")
    dc.on_session_finished("sess-other")
    assert dc.get_active("sess-A") is not None


# --- typed requests have no session yet --------------------------------------

def test_an_unowned_dialogue_is_answerable_until_adopted():
    """A typed request opens a dialogue before any voice session exists."""
    dc.open_dialogue(question="What should I name it?", source="ui")
    assert dc.get_active("any-session") is not None


def test_the_session_started_for_the_capture_becomes_the_owner():
    dc.open_dialogue(question="What should I name it?", source="ui")
    assert dc.adopt_session("sess-new") is True
    assert dc.get_active("sess-new") is not None
    assert dc.get_active("sess-other") is None, "adoption did not establish ownership"


def test_an_owned_dialogue_is_never_re_homed():
    dc.open_dialogue(question="What should I name it?", session_id="sess-A")
    assert dc.adopt_session("sess-B") is False
    assert dc.get_active("sess-A") is not None


# --- durable capture request -------------------------------------------------

def test_capture_stays_pending_until_acknowledged():
    """A boolean could not express "requested but not yet started", so the
    request was cleared while NEXI was still speaking the question."""
    dc.open_dialogue(question="What should I name it?", session_id="sess-A")

    dc.set_capture_state(CaptureState.REQUESTED)
    assert dc.capture_is_pending() is True
    dc.set_capture_state(CaptureState.QUEUED)
    assert dc.capture_is_pending() is True
    dc.set_capture_state(CaptureState.CAPTURE_STARTED)
    assert dc.capture_is_pending() is True


@pytest.mark.parametrize("terminal", [
    CaptureState.COMPLETED, CaptureState.NO_SPEECH,
    CaptureState.CANCELLED, CaptureState.FAILED,
])
def test_capture_stops_pending_only_at_a_terminal_state(terminal):
    dc.open_dialogue(question="q", session_id="sess-A")
    dc.set_capture_state(CaptureState.REQUESTED)
    dc.set_capture_state(terminal)
    assert dc.capture_is_pending() is False


# --- field collection --------------------------------------------------------

def test_collecting_fields_tracks_what_is_still_missing():
    dc.open_dialogue(question="What should I name it, and where?",
                     session_id="sess-A", workflow_id="create_folder",
                     required_fields=["folder_name", "folder_location"])

    ctx = dc.collect_field("folder_name", "Project Alpha", session_id="sess-A")
    assert ctx.missing_fields() == ["folder_location"]
    assert ctx.status is DialogueStatus.COLLECTING_INFORMATION

    ctx = dc.collect_field("folder_location", "Desktop", session_id="sess-A")
    assert ctx.missing_fields() == []
    assert ctx.status is DialogueStatus.READY_TO_EXECUTE


# --- expiry ------------------------------------------------------------------

def test_an_expired_dialogue_is_not_answerable():
    ctx = dc.open_dialogue(question="q", session_id="sess-A", ttl_seconds=1.0)
    ctx.expires_at = time.time() - 0.1
    assert dc.get_active("sess-A") is None


def test_cancel_makes_it_unanswerable():
    dc.open_dialogue(question="q", session_id="sess-A")
    dc.cancel_dialogue("user said cancel")
    assert dc.get_active("sess-A") is None
