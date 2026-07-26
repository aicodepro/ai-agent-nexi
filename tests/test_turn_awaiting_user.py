"""Speaking a question must not cancel waiting for its answer.

Live trace from a real session (create a folder):
    [TURN] auto_listen requested reason=assistant_question
    [TURN] state=speaking          <- mark_assistant_speaking overwrote _state
    [TURN] state=idle              <- mark_assistant_done's guard missed, cleared

_state was one variable serving two purposes: voice phase AND dialogue status.
mark_assistant_done() guarded on `_state != "waiting_for_user_answer"`, but
speaking had already replaced that value, so every spoken question discarded its
own auto-listen request.
"""
from __future__ import annotations

import pytest

from engine import turn_manager as tm


_MODULE_STATE = (
    "_state", "_last_question", "_reason", "_workflow_id",
    "_auto_listen_requested", "_awaiting_user",
    "_interrupted", "_interrupt_source", "_interrupt_reason",
)


@pytest.fixture(autouse=True)
def _reset():
    """turn_manager is process-global; snapshot and restore so these tests
    cannot leak dialogue state into unrelated suites."""
    saved = {name: getattr(tm, name) for name in _MODULE_STATE}
    tm.clear_waiting_for_user("test-setup")
    tm.mark_user_turn_started("test")
    yield
    for name, value in saved.items():
        setattr(tm, name, value)


def test_speaking_a_question_preserves_the_wait():
    """The exact live sequence: ask -> speak -> done."""
    tm.mark_waiting_for_user("What should I name the folder?",
                             reason="missing_slot", workflow_id="create_folder")
    assert tm.should_auto_listen() is True

    tm.mark_assistant_speaking("What should I name the folder?")
    assert tm.is_awaiting_user() is True, "speaking destroyed the dialogue status"

    tm.mark_assistant_done("What should I name the folder?")
    assert tm.should_auto_listen() is True, "TTS completion discarded the auto-listen request"
    assert tm.is_awaiting_user() is True


def test_question_details_survive_the_whole_speak_cycle():
    tm.mark_waiting_for_user("Where should I create it?",
                             reason="missing_slot", workflow_id="create_folder")
    tm.mark_assistant_speaking()
    tm.mark_assistant_done()

    state = tm.get_turn_state()
    assert state["workflow_id"] == "create_folder"
    assert "Where should I create it" in state["last_question"]
    assert state["awaiting_user"] is True


def test_a_plain_statement_still_ends_the_turn():
    """No question pending: speaking then finishing must return to idle."""
    tm.mark_assistant_speaking("The time is four o'clock.")
    tm.mark_assistant_done("The time is four o'clock.")

    assert tm.should_auto_listen() is False
    assert tm.is_awaiting_user() is False
    assert tm.get_turn_state()["state"] == "idle"


def test_the_user_answering_ends_the_wait():
    tm.mark_waiting_for_user("What should I name it?", reason="missing_slot")
    tm.mark_assistant_speaking()
    tm.mark_assistant_done()

    tm.mark_user_turn_started("hotword")
    assert tm.is_awaiting_user() is False, "the wait must end once the user speaks"
    assert tm.should_auto_listen() is False


def test_wait_can_be_cleared_explicitly():
    tm.mark_waiting_for_user("What should I name it?", reason="missing_slot")
    tm.clear_waiting_for_user("cancelled")

    assert tm.is_awaiting_user() is False
    assert tm.should_auto_listen() is False
    assert tm.get_turn_state()["workflow_id"] == ""


def test_interrupt_ends_the_wait():
    """Barge-in cancels the question rather than leaving it dangling."""
    tm.mark_waiting_for_user("What should I name it?", reason="missing_slot")
    tm.request_interrupt("hotword", "hotword_during_speaking")
    tm.clear_interrupt()

    assert tm.is_awaiting_user() is False
    assert tm.should_auto_listen() is False
