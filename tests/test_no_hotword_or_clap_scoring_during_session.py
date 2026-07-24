from __future__ import annotations


class CountingScorer:
    name = "openwakeword"

    def __init__(self):
        self.calls = 0

    def score(self, frame: bytes) -> float:
        self.calls += 1
        return 1.0


def test_no_hotword_or_clap_scoring_during_session():
    from engine.audio_wake_pipeline import AudioWakePipeline
    from engine.wake_session_manager import finish_session, start_session

    finish_session("test_reset")
    scorer = CountingScorer()
    start_session("hotword")
    try:
        pipeline = AudioWakePipeline(wake_scorer=scorer, enable_clap=True)
        result = pipeline.process_frame(b"\x00\x00" * 1280)
        assert result["wake"] is False
        assert result["reason"] == "session_active"
        assert scorer.calls == 0
        assert pipeline._clap_manager is None
    finally:
        finish_session("test_cleanup")

