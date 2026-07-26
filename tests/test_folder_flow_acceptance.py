"""Reference acceptance: the create-folder conversation, end to end.

This is the scenario that failed in a real session and drove six separate
repairs. It exists so the pieces are proven to work TOGETHER, not just
individually - each fix below had its own passing unit test while the actual
conversation still dead-ended.

    User: Create a folder.
    NEXI: What should I name the folder?
    [listening]
    User: Project Alpha
    NEXI: Where should I create it?
    User: Desktop
    NEXI: creates and verifies

The defects this pins down, in the order the conversation hits them:
  1. a typed request produced no session, so the mic could never open;
  2. "ui" was not an auto-listen source;
  3. speaking the question erased the auto-listen request;
  4. the session slept 3s after asking, discarding the pending question;
  5. saying "Create a folder" again was stored AS the folder's name;
  6. a silent follow-up emitted speech_ended from LISTENING.
"""
from __future__ import annotations

import queue
from unittest.mock import patch

import pytest

from engine import runtime_bridge, turn_manager as tm, wake_session_manager as wsm
from engine.command import _FOLLOWUP_SOURCES
from engine.create_folder_workflow import validate_folder_name
from engine.followup_manager import set_pending_followup, clear_followup, has_pending_followup


_TM_STATE = ("_state", "_last_question", "_reason", "_workflow_id",
             "_auto_listen_requested", "_awaiting_user",
             "_interrupted", "_interrupt_source", "_interrupt_reason")


def _reset_turn_manager(label: str) -> None:
    """Version-tolerant reset.

    Deliberately does not require clear_waiting_for_user(): this file must be
    runnable against the pre-fix runtime so its assertions fail on BEHAVIOUR,
    not on a missing helper. A fixture that explodes on old code proves only
    that the API changed.
    """
    clear = getattr(tm, "clear_waiting_for_user", None)
    if callable(clear):
        clear(label)
    else:  # pre-fix runtime
        tm.mark_assistant_done("")


@pytest.fixture(autouse=True)
def _isolate():
    saved = {n: getattr(tm, n, None) for n in _TM_STATE}
    clear_followup("acceptance-setup")
    _reset_turn_manager("acceptance-setup")
    yield
    clear_followup("acceptance-teardown")
    for n, v in saved.items():
        if v is not None or hasattr(tm, n):
            setattr(tm, n, v)


# --- step 1: the request arrives, typed --------------------------------------

def test_step1_typed_source_can_request_the_microphone():
    assert "ui" in _FOLLOWUP_SOURCES, "typed requests cannot auto-listen"


def test_step2_typed_request_queues_a_capture_with_a_session():
    q = queue.Queue()
    assert runtime_bridge.post_followup_capture(q, "", source="ui", reason="missing_slot") is True
    event = q.get_nowait()
    assert event["start_session"] is True, "the capture had no session and would be dropped"


# --- step 3: NEXI asks, and speaks the question ------------------------------

def test_step3_speaking_the_question_preserves_the_wait():
    tm.mark_waiting_for_user("What should I name the folder?",
                             reason="missing_slot", workflow_id="create_folder")
    tm.mark_assistant_speaking()
    tm.mark_assistant_done()

    assert tm.should_auto_listen() is True, "speaking the question erased the auto-listen request"
    assert getattr(tm, "is_awaiting_user", lambda: tm.get_turn_state().get("awaiting_user"))() is True


# --- step 4: NEXI waits for a human to answer --------------------------------

def test_step4_session_does_not_sleep_before_the_user_answers():
    set_pending_followup("What should I name the folder?", "folder_name", "acceptance")
    manager = wsm.WakeSessionManager()
    manager._session_id = "sess-acceptance"
    manager._has_spoken = True
    import time
    manager._last_event_at = time.time() - (wsm._AUTO_FINISH_TIMEOUT_SECONDS + 1.0)

    assert manager.check_timeout() is False, "slept before the user could answer"
    assert manager._session_id == "sess-acceptance"
    assert has_pending_followup() is True, "the pending question was discarded"


# --- step 5: the answer is bound to the right slot ---------------------------

def test_step5_a_real_name_is_accepted():
    assert validate_folder_name("Project Alpha") is None


def test_step5_repeating_the_command_is_not_a_name():
    """The live failure: "Create a folder" was saved as the folder's name."""
    for said in ["Create a folder", "create folder", "new folder"]:
        assert validate_folder_name(said) is not None, f"{said!r} accepted as a name"


# --- step 6: the user says nothing -------------------------------------------

def test_step6_silence_uses_a_valid_transition(capsys):
    from engine.voice_state_machine import VoiceState, VoiceStateMachine

    m = VoiceStateMachine()
    m.transition("wake_detected", source="hotword")
    m.transition("listening_started", source="hotword")
    m.transition("no_speech_timeout", source="hotword")

    assert "no_valid_transition" not in capsys.readouterr().out
    assert m.get_voice_state() is VoiceState.LISTENING


def test_step6_silence_does_not_announce_recognising():
    from engine.ui_state_manager import STATE_ALIASES
    assert STATE_ALIASES.get("no_speech_timeout") == "listening"


# --- the whole conversation, as one ordered sequence -------------------------

def test_full_conversation_never_loses_the_question():
    """Ask -> speak -> finish speaking -> still waiting, still listening.

    Every individual fix had a green test while this sequence still failed,
    which is the entire reason this file exists.
    """
    q = queue.Queue()

    # NEXI decides it needs the folder name.
    tm.mark_waiting_for_user("What should I name the folder?",
                             reason="missing_slot", workflow_id="create_folder")
    set_pending_followup("What should I name the folder?", "folder_name", "ui")
    assert runtime_bridge.post_followup_capture(q, "", source="ui", reason="missing_slot")

    # NEXI speaks it.
    tm.mark_assistant_speaking()
    tm.mark_assistant_done()

    # The turn must still be waiting, still want the mic, and still hold the slot.
    assert getattr(tm, "is_awaiting_user", lambda: tm.get_turn_state().get("awaiting_user"))() is True
    assert tm.should_auto_listen() is True
    assert has_pending_followup() is True
    assert tm.get_turn_state()["workflow_id"] == "create_folder"
    assert q.get_nowait()["start_session"] is True

    # The user answers; the wait ends exactly once.
    tm.mark_user_turn_started("hotword")
    assert getattr(tm, "is_awaiting_user", lambda: tm.get_turn_state().get("awaiting_user"))() is False
    assert tm.should_auto_listen() is False


def test_a_new_root_command_is_not_swallowed_as_the_answer():
    """"Create a folder" said at the name prompt must not become the name."""
    tm.mark_waiting_for_user("What should I name the folder?",
                             reason="missing_slot", workflow_id="create_folder")
    set_pending_followup("What should I name the folder?", "folder_name", "ui")

    assert validate_folder_name("Create a folder") is not None
