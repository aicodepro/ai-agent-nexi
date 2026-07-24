import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ScriptedScorer:
    model_name = "hey nexi"

    def __init__(self, scores):
        self.scores = list(scores)
        self.index = 0

    def score(self, frame):
        value = self.scores[min(self.index, len(self.scores) - 1)]
        self.index += 1
        return value


def test_hotword_and_double_clap_candidates_share_arbitration(monkeypatch):
    monkeypatch.setenv("NEXI_CLAP_ENABLED", "true")
    monkeypatch.setenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.5")
    monkeypatch.setenv("OPENWAKEWORD_CONSECUTIVE_HITS", "1")
    import engine.audio_wake_pipeline as awp
    importlib.reload(awp)

    clock = FakeClock()
    pipeline = awp.AudioWakePipeline(wake_scorer=ScriptedScorer([0.9, 0.0]), clock=clock, enable_clap=True)
    hotword = pipeline.process_frame(b"\x00\x00" * 1280)
    assert hotword["wake"] is True
    assert hotword["source"] == "hotword"

    clock.advance(0.1)
    clap = pipeline._evaluate_wake_candidate("double_clap", True, 1.0, clock(), "test")
    assert clap.should_wake is False
    # WakeOrchestrator's default allow_sources is "hotword,double_clap,hotkey" (its
    # own docstring: "OR logic: hotword OR double_clap OR hotkey") — double_clap is
    # always an allowed source. 100ms after the hotword wake, a same-arbitrator
    # double_clap candidate is correctly suppressed by cooldown, not by source.
    assert clap.reason == "cooldown"
