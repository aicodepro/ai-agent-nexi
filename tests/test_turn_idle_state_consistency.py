def test_clear_interrupt_removes_stale_waiting_state_when_returning_idle():
    from engine import turn_manager

    turn_manager.mark_waiting_for_user("Which app?", reason="clarification", workflow_id="open_app")
    turn_manager.request_interrupt("typed", "new_command")
    turn_manager.clear_interrupt()

    state = turn_manager.get_turn_state()
    assert state["state"] == "idle"
    assert state["last_question"] == ""
    assert state["reason"] == ""
    assert state["workflow_id"] == ""
    assert state["auto_listen_requested"] is False
    assert state["interrupted"] is False


def test_assistant_done_clears_interrupt_flags_when_returning_idle():
    from engine import turn_manager

    turn_manager.request_interrupt("hotword", "barge_in")
    turn_manager.mark_assistant_done()

    state = turn_manager.get_turn_state()
    assert state["state"] == "idle"
    assert state["interrupted"] is False
    assert state["interrupt_source"] == ""
    assert state["interrupt_reason"] == ""
