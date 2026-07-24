from __future__ import annotations

from engine.wake_session_manager import (
    WakeSessionManager,
    get_session_manager,
    start_session,
    is_session_active,
    is_current_session,
    are_detectors_paused,
    finish_session,
    ignore_if_stale,
)


def _reset():
    mgr = WakeSessionManager.get_instance()
    mgr._session_id = None
    mgr._source = ""
    mgr._state = "sleep"
    mgr._detectors_paused = False
    mgr._started_at = 0.0
    mgr._last_event_at = 0.0


def test_start_session_returns_id():
    _reset()
    sid = start_session("hotword")
    assert sid is not None
    assert len(sid) == 8
    assert is_session_active()


def test_start_session_twice_returns_same():
    _reset()
    sid1 = start_session("hotword")
    sid2 = start_session("clap")
    assert sid1 == sid2
    assert is_session_active()


def test_pauses_detectors_on_start():
    _reset()
    start_session("hotword")
    assert are_detectors_paused()


def test_finish_session_resumes_detectors():
    _reset()
    start_session("hotword")
    assert are_detectors_paused()
    finish_session("complete")
    assert not are_detectors_paused()
    assert not is_session_active()


def test_is_current_session():
    _reset()
    sid = start_session("hotword")
    assert is_current_session(sid)
    assert not is_current_session("other")


def test_ignore_if_stale_mismatch():
    _reset()
    sid = start_session("hotword")
    assert not ignore_if_stale(sid)
    assert ignore_if_stale("wrong_id")


def test_ignore_if_stale_no_session():
    _reset()
    assert ignore_if_stale("any_id") is False


def test_get_session_id():
    _reset()
    assert get_session_manager().get_session_id() is None
    sid = start_session("hotword")
    assert get_session_manager().get_session_id() == sid


def test_set_state():
    _reset()
    start_session("hotword")
    manager = get_session_manager()
    manager.set_state("thinking")
    assert manager.get_state() == "thinking"


def test_get_source():
    _reset()
    start_session("double_clap")
    assert get_session_manager().get_source() == "double_clap"


def test_pause_resume_detectors():
    _reset()
    mgr = get_session_manager()
    mgr.pause_detectors()
    assert mgr.are_detectors_paused()
    mgr.resume_detectors()
    assert not mgr.are_detectors_paused()


def test_check_timeout_no_session():
    _reset()
    assert not get_session_manager().check_timeout()


def test_finish_with_reason_logging():
    _reset()
    start_session("hotword")
    assert is_session_active()
    finish_session("test_complete")
    assert not is_session_active()
    assert not are_detectors_paused()


def test_multiple_finish_safe():
    _reset()
    finish_session("cleanup")
    finish_session("again")
    assert not is_session_active()


def test_session_blocks_second_start():
    _reset()
    sid1 = start_session("hotword")
    sid2 = start_session("clap")
    assert sid1 == sid2
    finish_session("complete")
    sid3 = start_session("clap")
    assert sid3 != sid1
