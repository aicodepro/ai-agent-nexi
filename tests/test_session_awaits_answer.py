"""A pending question must not be slept away before the user can answer.

Live regression: "create a folder" -> NEXI asks "What should I name it?" ->
[SESSION] auto_timeout_finish idle_seconds=3.0 three seconds later, and the
timeout path CLEARS the pending question. Every clarification was a dead end,
so NEXI could never gather a missing slot by voice.
"""
from __future__ import annotations

import time

import pytest

from engine import wake_session_manager as wsm


@pytest.fixture(autouse=True)
def _clean_state():
    from engine.clarification_manager import clear_clarification
    from engine.followup_manager import clear_followup
    clear_clarification("test")
    clear_followup("test")
    yield
    clear_clarification("test")
    clear_followup("test")


def test_answer_window_is_longer_than_the_plain_re_arm():
    assert wsm._AWAITING_ANSWER_TIMEOUT_SECONDS > wsm._AUTO_FINISH_TIMEOUT_SECONDS
    assert wsm._AWAITING_ANSWER_TIMEOUT_SECONDS >= 10.0, "a human needs time to answer"


def test_no_question_pending_by_default():
    assert wsm._question_is_pending() is False


def test_pending_followup_is_a_question():
    from engine.followup_manager import set_pending_followup

    set_pending_followup("What should I name the folder?", "folder_name", "test")
    assert wsm._question_is_pending() is True


def test_pending_clarification_is_a_question():
    from engine.clarification_manager import ask_clarification

    ask_clarification("open")
    assert wsm._question_is_pending() is True


def _session_idle_for(manager, seconds: float) -> None:
    """Age the session so the idle check sees `seconds` of inactivity."""
    manager._last_event_at = time.time() - seconds
    manager._has_spoken = True


def test_question_survives_the_three_second_re_arm():
    """The exact live failure: asked at t=0, asleep at t=3."""
    from engine.followup_manager import set_pending_followup

    manager = wsm.WakeSessionManager()
    manager._session_id = "sess-q"
    set_pending_followup("What should I name the folder?", "folder_name", "test")
    _session_idle_for(manager, wsm._AUTO_FINISH_TIMEOUT_SECONDS + 1.0)

    assert manager.check_timeout() is False, "slept before the user could answer"
    assert manager._session_id == "sess-q"


def test_statement_still_re_arms_quickly():
    """No question pending: the short re-arm must be preserved."""
    manager = wsm.WakeSessionManager()
    manager._session_id = "sess-s"
    _session_idle_for(manager, wsm._AUTO_FINISH_TIMEOUT_SECONDS + 1.0)

    assert manager.check_timeout() is True
    assert manager._session_id is None


def test_unanswered_question_eventually_releases_detectors():
    """Bounded, not infinite - a walked-away user must not pin the mic open."""
    from engine.followup_manager import set_pending_followup

    manager = wsm.WakeSessionManager()
    manager._session_id = "sess-gone"
    set_pending_followup("What should I name the folder?", "folder_name", "test")
    _session_idle_for(manager, wsm._AWAITING_ANSWER_TIMEOUT_SECONDS + 1.0)

    assert manager.check_timeout() is True
    assert manager._session_id is None


# --- the command is not a folder name ---------------------------------------

def test_repeating_the_command_is_not_accepted_as_a_folder_name():
    """Live regression: "Create a folder" was saved AS the folder's name."""
    from engine.create_folder_workflow import validate_folder_name

    for said in ["Create a folder", "create folder", "new folder", "Make a folder"]:
        assert validate_folder_name(said) is not None, f"{said!r} was accepted as a name"


def test_real_folder_names_still_pass():
    from engine.create_folder_workflow import validate_folder_name

    for name in ["project alpha", "Invoices 2026", "nexi-notes", "Folder Ideas"]:
        assert validate_folder_name(name) is None, f"{name!r} should be a valid name"
