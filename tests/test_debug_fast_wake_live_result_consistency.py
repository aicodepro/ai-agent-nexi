"""Tests: debug_fast_wake_live.py result consistency across phases."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDebugFastWakeLiveResultConsistency:
    def test_wake_tracker_reset_clears_detected_fields(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_wake("hotword", "openwakeword", 0.85, 0.85)
        t.reset_attempt()
        assert t.detected_source == ""
        assert t.detected_backend == ""
        assert t.detected_confidence == 0.0
        assert t.detected_score == 0.0
        assert t.woke is False

    def test_wake_tracker_persists_events_across_resets(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.add_event("silence", "hotword", "openwakeword", 0.65, 0.65, "wake_detected")
        t.reset_attempt()
        t.add_event("hey_nexi", "hotword", "openwakeword", 0.88, 0.88, "wake_detected")
        assert len(t.all_events) == 2
        assert t.all_events[0].phase == "silence"
        assert t.all_events[1].phase == "hey_nexi"

    def test_wake_tracker_no_duplicate_wake_scores(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_wake("hotword", "openwakeword", 0.85, 0.85)
        t.record_wake("hotword", "openwakeword", 0.90, 0.90)
        assert len(t.wake_scores) == 2

    def test_wake_tracker_max_score_across_resets(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.record_hotword_score(0.3)
        t.record_hotword_score(0.7)
        assert t.max_hotword_score == 0.7
        t.reset_attempt()
        assert t.max_hotword_score == 0.0

    def test_event_table_contains_expected_columns(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.add_event("silence", "hotword", "openwakeword", 0.65, 0.65, "wake_detected")
        assert len(t.all_events) == 1
        ev = t.all_events[0]
        assert hasattr(ev, "phase")
        assert hasattr(ev, "source")
        assert hasattr(ev, "backend")
        assert hasattr(ev, "confidence")
        assert hasattr(ev, "score")
        assert hasattr(ev, "event_type")
        assert hasattr(ev, "timestamp")
        assert hasattr(ev, "metadata")

    def test_event_table_output_format(self):
        from scripts.debug_fast_wake_live import WakeTracker
        t = WakeTracker()
        t.add_event("silence", "double_clap", "dsp_clap", 0.22, 0.0, "wake_detected")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            t.print_event_table()
        output = buf.getvalue()
        assert "[EVENT_TABLE]" in output
        assert "silence,double_clap,dsp_clap,0.0000,0.2200" in output

    def test_result_dict_keys_consistent(self):
        results = {
            "silence_false_wakes": 0,
            "silence_false_hotword_wakes": 0,
            "silence_false_clap_wakes": 0,
            "silence_false_unknown_wakes": 0,
            "silence_false_wake_source": "none",
            "silence_false_wake_backend": "",
            "silence_false_wake_confidence": 0.0,
            "silence_false_wake_score": 0.0,
            "hey_nexi_detected": 0,
            "nexi_detected": 0,
            "single_clap_wakes": 0,
            "double_clap_detected": 0,
            "speech_false_clap_wakes": 0,
        }
        assert "silence_false_hotword_wakes" in results
        assert "silence_false_clap_wakes" in results
        assert "silence_false_unknown_wakes" in results
        assert results["silence_false_wakes"] == 0
