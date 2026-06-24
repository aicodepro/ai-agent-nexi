from __future__ import annotations


def test_detectors_pause_after_wake():
    from engine.wake_session_manager import are_detectors_paused, finish_session, start_session

    finish_session("test_reset")
    sid = start_session("hotword")
    try:
        assert sid
        assert are_detectors_paused()
    finally:
        finish_session("test_cleanup")

