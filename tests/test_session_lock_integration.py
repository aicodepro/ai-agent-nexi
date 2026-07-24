from __future__ import annotations

"""Test that session lock pauses wake detection at the pipeline level."""

from engine.wake_session_manager import WakeSessionManager, start_session, finish_session


def _reset():
    mgr = WakeSessionManager.get_instance()
    mgr._session_id = None
    mgr._source = ""
    mgr._state = "sleep"
    mgr._detectors_paused = False
    mgr._started_at = 0.0
    mgr._last_event_at = 0.0


def make_pipeline():
    from engine.audio_wake_pipeline import AudioWakePipeline
    return AudioWakePipeline(
        wake_scorer=type("FakeScorer", (), {"name": "test", "score": lambda self, x: 0.9})(),
        clock=__import__("time").time,
    )


def test_pipeline_returns_session_active_during_session():
    _reset()
    start_session("hotword")
    pl = make_pipeline()
    result = pl.process_frame(b"\x00\x00" * 640)
    assert result.get("reason") == "session_active"
    assert not result.get("wake")
    finish_session("test")


def test_pipeline_works_after_session():
    _reset()
    pl = make_pipeline()
    result = pl.process_frame(b"\x00\x00" * 640)
    assert result.get("reason") != "session_active"


def test_start_session_pauses_detectors():
    _reset()
    start_session("hotword")
    session_mgr = WakeSessionManager.get_instance()
    assert session_mgr.are_detectors_paused()
    finish_session("test")
    assert not session_mgr.are_detectors_paused()


def test_session_id_isolation():
    _reset()
    sid1 = start_session("hotword")
    from engine.wake_session_manager import is_current_session
    assert is_current_session(sid1)
    finish_session("test")
    sid2 = start_session("clap")
    assert sid2 != sid1
    assert is_current_session(sid2)
