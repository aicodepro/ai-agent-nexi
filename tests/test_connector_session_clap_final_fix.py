from __future__ import annotations

import queue
import time
from unittest.mock import patch


class ScriptedScorer:
    name = "scripted"

    def __init__(self, score: float = 0.9):
        self.score_value = score

    def score(self, frame: bytes) -> float:
        return self.score_value


def _frame(samples: int = 1280) -> bytes:
    return b"\x00\x00" * samples


def _reset_session() -> None:
    from engine.wake_session_manager import WakeSessionManager

    mgr = WakeSessionManager.get_instance()
    mgr._session_id = None
    mgr._source = ""
    mgr._state = "sleep"
    mgr._detectors_paused = False
    mgr._started_at = 0.0
    mgr._last_event_at = 0.0
    mgr._last_finished_at = 0.0


def test_process_frame_does_not_emit_ui_wake_before_session(monkeypatch):
    import engine.audio_wake_pipeline as awp

    _reset_session()
    monkeypatch.setattr(awp, "OWW_THRESHOLD", 0.5)
    monkeypatch.setattr(awp, "OWW_CONSECUTIVE", 1)

    q: queue.Queue = queue.Queue()
    pipeline = awp.AudioWakePipeline(
        wake_scorer=ScriptedScorer(0.9),
        command_queue=q,
        clock=lambda: time.time(),
    )

    result = pipeline.process_frame(_frame())

    assert result["wake"] is True
    assert result["source"] == "hotword"
    assert q.empty()


def test_trigger_wake_posts_wake_and_listening_with_session_id(monkeypatch):
    import engine.audio_wake_pipeline as awp
    from engine.wake_session_manager import finish_session

    _reset_session()
    monkeypatch.setattr(awp, "POST_WAKE_DELAY_MS", 0)
    monkeypatch.setattr(awp, "ASR_MIN_AUDIO_MS", 100)

    q: queue.Queue = queue.Queue()
    pipeline = awp.AudioWakePipeline(
        wake_scorer=ScriptedScorer(0.0),
        command_queue=q,
        clock=lambda: time.time(),
    )

    def fake_capture(_next_frame, source="hotword"):
        pipeline._last_capture_stats = {
            "duration_ms": 200,
            "speech_ms": 160,
            "speech_started": True,
            "source": source,
        }
        return b"\x01\x00" * int(awp.SAMPLE_RATE * 0.2)

    try:
        with patch.object(pipeline, "capture_command", side_effect=fake_capture), \
             patch.object(pipeline, "emit_command", return_value="hello"), \
             patch("engine.nexi_wake_controller.wake_nexi", return_value=True):
            assert pipeline.trigger_wake("hotword", already_arbitrated=True, confidence=0.87, reason="threshold") is True

        events = [q.get_nowait(), q.get_nowait()]
        assert [(event["status"], event["source"]) for event in events] == [
            ("wake_detected", "hotword"),
            ("listening", "hotword"),
        ]
        assert events[0]["session_id"]
        assert events[1]["session_id"] == events[0]["session_id"]
    finally:
        finish_session("test")
        _reset_session()


def test_bridge_status_can_carry_explicit_session_id():
    from engine.runtime_bridge import post_status

    q: queue.Queue = queue.Queue()
    assert post_status(q, "wake_detected", source="hotword", session_id="sess123") is True
    event = q.get_nowait()
    assert event["session_id"] == "sess123"


def test_ui_ack_wait_uses_session_id():
    from engine.ui_state_ack import on_ui_state_ack, reset_acks, wait_for_ack

    reset_acks()
    on_ui_state_ack("online", "sess123", 0.0, label="ONLINE")
    assert wait_for_ack("online", "sess123", timeout_ms=50) is True


def test_default_asr_saves_last_request_wav(monkeypatch, tmp_path):
    import engine.audio_wake_pipeline as awp

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("engine.groq_asr.transcribe_audio_bytes", lambda wav: "ok")

    assert awp._default_asr(b"\x00\x00" * 1600, 16000) == "ok"
    saved = tmp_path / "artifacts" / "last_asr_request.wav"
    assert saved.exists()
    assert saved.read_bytes().startswith(b"RIFF")


def test_post_session_wake_suppression_blocks_residual_hotword(monkeypatch):
    import engine.audio_wake_pipeline as awp
    from engine.wake_session_manager import finish_session, start_session

    _reset_session()
    monkeypatch.setattr(awp, "OWW_THRESHOLD", 0.5)
    monkeypatch.setattr(awp, "OWW_CONSECUTIVE", 1)

    start_session("hotword")
    finish_session("asr_empty")

    pipeline = awp.AudioWakePipeline(
        wake_scorer=ScriptedScorer(0.9),
        clock=lambda: time.time(),
    )
    result = pipeline.process_frame(_frame())

    assert result["wake"] is False
    assert result["reason"] == "post_session_suppressed"
    _reset_session()


def test_bridge_completion_reaches_audio_session_manager():
    import engine.audio_wake_pipeline as awp
    from engine.runtime_bridge import post_session_finish
    from engine.wake_session_manager import get_session_manager, start_session

    _reset_session()
    control_queue: queue.Queue = queue.Queue()
    session_id = start_session("hotword")
    pipeline = awp.AudioWakePipeline(control_queue=control_queue)

    assert post_session_finish(control_queue, session_id) is True
    assert pipeline._drain_control_events() == 1
    assert get_session_manager().is_active() is False
    assert get_session_manager().is_post_session_suppressed() is True
    _reset_session()


def test_followup_control_reaches_audio_capture_for_current_session():
    import engine.audio_wake_pipeline as awp
    from engine.runtime_bridge import post_followup_capture
    from engine.wake_session_manager import start_session

    _reset_session()
    control_queue: queue.Queue = queue.Queue()
    session_id = start_session("hotword")
    pipeline = awp.AudioWakePipeline(control_queue=control_queue)

    assert post_followup_capture(
        control_queue,
        session_id,
        source="hotword",
        reason="missing_slot",
    ) is True
    with patch.object(pipeline, "_capture_followup", create=True, return_value=True) as capture:
        assert pipeline._drain_control_events() == 1

    capture.assert_called_once()
    event = capture.call_args.args[0]
    assert event["session_id"] == session_id
    assert event["reason"] == "missing_slot"
    _reset_session()


def _clap_event() -> dict:
    return {
        "clap": True,
        "wake": False,
        "source": None,
        "backend": "dsp_clap",
        "backend_used": "dsp_clap",
        "fallback_used": False,
        "cooldown": False,
        "amplitude": 0.5,
        "reason": "clap_detected",
    }


def test_double_clap_accepts_2238ms_gap_by_default(monkeypatch):
    monkeypatch.delenv("NEXI_CLAP_MAX_GAP_MS", raising=False)
    monkeypatch.delenv("CLAP_MAX_GAP_MS", raising=False)

    from engine.clap_backend_manager import ClapBackendManager

    manager = ClapBackendManager(clock=time.time, cooldown_ms=1500)
    now = time.time()
    assert manager._apply_double_clap_state(_clap_event(), now)["wake"] is False
    second = manager._apply_double_clap_state(_clap_event(), now + 2.238)

    assert second["wake"] is True
    assert second["source"] == "double_clap"
    assert 2230 <= second["gap_ms"] <= 2245


def test_late_double_clap_keeps_current_clap_as_new_first(monkeypatch):
    monkeypatch.delenv("NEXI_CLAP_MAX_GAP_MS", raising=False)
    monkeypatch.delenv("CLAP_MAX_GAP_MS", raising=False)

    from engine.clap_backend_manager import ClapBackendManager

    manager = ClapBackendManager(clock=time.time, cooldown_ms=1500)
    now = time.time()
    assert manager._apply_double_clap_state(_clap_event(), now)["wake"] is False

    # Second clap at now+5.0 (5000ms gap > 4500ms max_gap_ms → too_late → reset)
    late = manager._apply_double_clap_state(_clap_event(), now + 5.0)
    assert late["wake"] is False
    assert late["reject_reason"] == "too_late"
    state = manager._double_clap.get_status()["state"]
    assert state in ("idle", "reset"), f"Expected reset/idle after too_late, got {state}"

    # Third clap starts a new first-clap wait
    third = manager._apply_double_clap_state(_clap_event(), now + 6.0)
    assert third["wake"] is False

    # Fourth clap within max_gap_ms completes the double clap
    second = manager._apply_double_clap_state(_clap_event(), now + 6.8)
    assert second["wake"] is True
    assert second["source"] == "double_clap"
