"""Tests: debug_fast_wake_live.py reports detected score correctly (not 0)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDebugFastWakeLiveReportsDetectedScore:
    def test_tracker_reports_max_score_after_attempt(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        for score in [0.1, 0.3, 0.6, 0.9, 0.7]:
            t.record_hotword_score(score)
        t.record_wake(source="hotword", backend="openwakeword", confidence=0.9, score=0.9)
        assert t.detected_score == 0.9
        assert t.max_hotword_score == 0.9

    def test_detected_score_never_zero_when_wake(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_hotword_score(0.65)
        t.record_wake(source="hotword", backend="openwakeword", confidence=0.65, score=0.65)
        assert t.detected_score > 0.0
        assert t.max_hotword_score >= t.detected_score

    def test_max_score_tracks_highest(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_hotword_score(0.0)
        t.record_hotword_score(0.65)
        t.record_hotword_score(0.99)
        t.record_hotword_score(0.30)
        assert t.max_hotword_score == 0.99

    def test_missed_detection_prints_max_not_zero(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_hotword_score(0.0)
        t.record_hotword_score(0.48)
        t.record_hotword_score(0.32)
        assert t.max_hotword_score == 0.48
        assert t.woke is False
        assert t.detected_score == 0.0

    def test_tracker_resets_scores_correctly(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_hotword_score(0.9)
        t.record_wake(source="hotword", backend="openwakeword", confidence=0.9, score=0.9)
        t.reset_attempt()
        assert t.max_hotword_score == 0.0
        assert t.detected_score == 0.0
        assert t.frame_count == 0
        assert t.woke is False
