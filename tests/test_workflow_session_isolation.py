"""A question must not outlive the conversation that asked it.

The live leak:

    [UI]  create a folder
          -> [FOLLOWUP] set type=folder_name          (no session recorded)
    ... the user walks away, that turn ends ...
    [hotword] "Create a folder"                        (a NEW conversation)
          -> [FOLLOWUP] answer_received slot=folder_name value=Create a folder
          -> [WORKFLOW] slot_saved name=folder_name

followup_manager._pending is process-global with no session binding, so the new
session's FIRST command was consumed as the previous question's answer - and
became the folder's name.

Rejecting "Create a folder" as a folder name (already done) treats the symptom.
This pins the cause: ownership.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from engine import followup_manager as fm


@pytest.fixture(autouse=True)
def _reset():
    fm.clear_followup("test-setup")
    yield
    fm.clear_followup("test-teardown")


def _in_session(session_id: str):
    """Set the ambient session.

    Patches runtime_bridge.current_bridge_session_id, which exists in BOTH the
    pre-fix and post-fix runtime, rather than followup_manager's own helper
    which exists only after the fix. Patching a symbol that the old code lacks
    would make these tests fail with AttributeError against pre-fix code -
    proving the API changed and nothing about the leak.
    """
    return patch("engine.runtime_bridge.current_bridge_session_id",
                 return_value=session_id)


def test_a_question_asked_in_one_session_is_invisible_in_the_next():
    with _in_session("sess-A"):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        assert fm.has_pending_followup() is True

    with _in_session("sess-B"):
        assert fm.has_pending_followup() is False, \
            "a new conversation inherited the previous question"


def test_a_new_session_discards_a_question_it_did_not_ask():
    with _in_session("sess-A"):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")

    fm.on_session_started("sess-B")
    with _in_session("sess-B"):
        assert fm.has_pending_followup() is False


def test_the_new_command_is_not_consumed_as_the_old_answer():
    """The exact live failure, end to end."""
    with _in_session("sess-A"):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")

    fm.on_session_started("sess-B")
    with _in_session("sess-B"):
        result = fm.consume_followup_answer("Create a folder", source="hotword")

    assert result["handled"] is False, "the new command was eaten as the old answer"
    assert result["route"] == "none"


# --- the typed path must still work ------------------------------------------

def test_a_typed_question_is_adopted_by_the_session_opened_to_hear_it():
    """A typed request has no session yet; the capture session becomes owner."""
    with _in_session(""):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        fm.mark_capture_requested()

    fm.on_session_started("sess-capture")
    with _in_session("sess-capture"):
        assert fm.has_pending_followup() is True, \
            "the session opened to hear the answer discarded the question"
        result = fm.consume_followup_answer("Project Alpha", source="hotword")

    assert result["handled"] is True
    assert result["answer"] == "Project Alpha"


def test_a_typed_question_without_a_capture_request_is_still_discarded():
    """No microphone was requested, so a later wake is a NEW conversation."""
    with _in_session(""):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")

    fm.on_session_started("sess-later")
    with _in_session("sess-later"):
        assert fm.has_pending_followup() is False


def test_the_owning_session_can_still_answer_normally():
    with _in_session("sess-A"):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        fm.on_session_started("sess-A")  # same session, must be a no-op
        assert fm.has_pending_followup() is True
        result = fm.consume_followup_answer("Project Alpha", source="hotword")

    assert result["handled"] is True
    assert result["answer"] == "Project Alpha"


def test_no_session_context_does_not_block_answering():
    """Typed answer to a typed question: neither side has a session."""
    with _in_session(""):
        fm.set_pending_followup("What should I name the folder?", "folder_name", "ui")
        assert fm.has_pending_followup() is True
        assert fm.consume_followup_answer("Project Alpha", source="ui")["handled"] is True
