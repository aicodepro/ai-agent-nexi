from __future__ import annotations

import time

from engine.ui_state_ack import on_ui_state_ack, reset_acks, wait_for_ack


def test_ui_ack_function_exposed_in_command_py():
    import engine.command as cmd
    assert hasattr(cmd, "ui_state_ack")
    assert callable(cmd.ui_state_ack)


def test_ui_ack_call_stores_ack():
    reset_acks()
    import engine.command as cmd
    result = cmd.ui_state_ack(session_id="sess001", state="online", label="ONLINE")
    assert isinstance(result, dict)
    assert result.get("ok") is True
    assert result.get("session_id") == "sess001"
    assert result.get("state") == "online"
    assert wait_for_ack("online", "sess001", timeout_ms=50)


def test_ui_ack_call_stores_ack_for_listening():
    reset_acks()
    import engine.command as cmd
    cmd.ui_state_ack(session_id="sess002", state="listening", label="LISTENING")
    assert wait_for_ack("listening", "sess002", timeout_ms=50)


def test_ui_ack_call_stores_ack_for_recognising():
    reset_acks()
    import engine.command as cmd
    cmd.ui_state_ack(session_id="sess003", state="recognising", label="RECOGNISING")
    assert wait_for_ack("recognising", "sess003", timeout_ms=50)


def test_ui_ack_call_stores_ack_for_thinking():
    reset_acks()
    import engine.command as cmd
    cmd.ui_state_ack(session_id="sess004", state="thinking", label="THINKING")
    assert wait_for_ack("thinking", "sess004", timeout_ms=50)


def test_ui_ack_call_stores_ack_for_saying():
    reset_acks()
    import engine.command as cmd
    cmd.ui_state_ack(session_id="sess005", state="saying", label="SAYING")
    assert wait_for_ack("saying", "sess005", timeout_ms=50)


def test_ui_ack_returns_ok_with_empty_args():
    reset_acks()
    import engine.command as cmd
    result = cmd.ui_state_ack()
    assert isinstance(result, dict)
    assert result.get("ok") is True


def test_ui_ack_maps_js_call_to_on_ui_state_ack():
    reset_acks()
    from engine.ui_state_ack import get_last_ack
    import engine.command as cmd
    before = time.time()
    cmd.ui_state_ack(session_id="js-session", state="online", label="ONLINE")
    last = get_last_ack()
    assert "_last_any" in last
    assert last["_last_any"] >= before
