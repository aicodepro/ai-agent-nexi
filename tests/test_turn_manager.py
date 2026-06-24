import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_waiting_for_user_requests_auto_listen():
    from engine import turn_manager
    turn_manager.mark_user_turn_started("hotword")
    turn_manager.mark_waiting_for_user("What should I name it?", reason="missing_slot", workflow_id="create_folder")
    state = turn_manager.get_turn_state()
    assert state["state"] == "waiting_for_user_answer"
    assert state["auto_listen_requested"] is True
    assert turn_manager.consume_auto_listen_request() is True
    assert turn_manager.should_auto_listen() is False


def test_interrupt_state_records_source():
    from engine import turn_manager
    turn_manager.clear_interrupt()
    turn_manager.request_interrupt("typed", "new_command")
    state = turn_manager.get_turn_state()
    assert state["interrupted"] is True
    assert state["interrupt_source"] == "typed"
