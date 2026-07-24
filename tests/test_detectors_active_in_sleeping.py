from __future__ import annotations


def test_detectors_active_in_sleeping():
    from engine.wake_session_manager import are_detectors_paused, finish_session

    finish_session("test_reset")
    assert not are_detectors_paused()

