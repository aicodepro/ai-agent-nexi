"""Tests: debug_fast_wake_live.py records and reports wake source correctly."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDebugFastWakeLiveWakeSource:
    def test_tracker_records_wake_source(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_wake(source="hotword", backend="openwakeword", confidence=0.85, score=0.85)
        assert t.woke is True
        assert t.detected_source == "hotword"
        assert t.detected_backend == "openwakeword"
        assert t.detected_confidence == 0.85
        assert t.detected_score == 0.85

    def test_tracker_records_double_clap_wake(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_wake(source="double_clap", backend="dsp_clap", confidence=0.92, score=0.0)
        assert t.woke is True
        assert t.detected_source == "double_clap"
        assert t.detected_backend == "dsp_clap"

    def test_tracker_resets_between_attempts(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_wake(source="hotword", backend="openwakeword", confidence=0.85, score=0.85)
        t.reset_attempt()
        assert t.woke is False
        assert t.max_hotword_score == 0.0
        assert t.detected_source == ""

    def test_tracker_accumulates_max_score(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_hotword_score(0.1)
        t.record_hotword_score(0.5)
        t.record_hotword_score(0.3)
        assert t.max_hotword_score == 0.5
        assert t.frame_count == 3

    def test_tracker_stores_multiple_wake_events(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_wake(source="hotword", backend="openwakeword", confidence=0.85, score=0.85)
        assert len(t.wake_scores) == 1
        assert t.wake_scores[0]["source"] == "hotword"

    def test_wake_tracker_unaffected_by_silence_scores(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        for _ in range(100):
            t.record_hotword_score(0.01)
            t.record_hotword_score(0.02)
        assert t.max_hotword_score == 0.02
        assert t.woke is False
