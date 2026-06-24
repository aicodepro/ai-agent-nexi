from __future__ import annotations


class AlwaysWakeScorer:
    name = "openwakeword"

    def score(self, frame: bytes) -> float:
        raise AssertionError("hotword scorer should not run during an active session")


def test_no_rewake_during_asr_tts():
    from engine.audio_wake_pipeline import AudioWakePipeline
    from engine.wake_session_manager import finish_session, session_set_state, start_session

    finish_session("test_reset")
    start_session("hotword")
    try:
        pipeline = AudioWakePipeline(wake_scorer=AlwaysWakeScorer(), enable_clap=True)
        for state in ["recognising", "thinking", "saying"]:
            session_set_state(state)
            result = pipeline.process_frame(b"\x00\x00" * 1280)
            assert result["wake"] is False
            assert result["reason"] == "session_active"
    finally:
        finish_session("test_cleanup")

