from __future__ import annotations


def test_detectors_resume_after_sleeping():
    from engine.wake_session_manager import are_detectors_paused, finish_session, start_session

    finish_session("test_reset")
    start_session("double_clap")
    assert are_detectors_paused()
    finish_session("sleeping")
    assert not are_detectors_paused()

