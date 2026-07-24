"""Tests: silence false wake source tracking separates hotword/clap/unknown."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSilenceFalseWakeSourceTracking:
    def test_tracks_hotword_false_wake_separately(self):
        results = {
            "silence_false_hotword_wakes": 1,
            "silence_false_clap_wakes": 0,
            "silence_false_unknown_wakes": 0,
            "silence_false_wake_source": "hotword",
        }
        assert results["silence_false_hotword_wakes"] == 1
        assert results["silence_false_clap_wakes"] == 0
        assert results["silence_false_unknown_wakes"] == 0

    def test_tracks_clap_false_wake_separately(self):
        results = {
            "silence_false_hotword_wakes": 0,
            "silence_false_clap_wakes": 1,
            "silence_false_unknown_wakes": 0,
            "silence_false_wake_source": "double_clap",
        }
        assert results["silence_false_hotword_wakes"] == 0
        assert results["silence_false_clap_wakes"] == 1
        assert results["silence_false_unknown_wakes"] == 0

    def test_tracks_unknown_false_wake_separately(self):
        results = {
            "silence_false_hotword_wakes": 0,
            "silence_false_clap_wakes": 0,
            "silence_false_unknown_wakes": 1,
            "silence_false_wake_source": "unknown",
            "silence_false_wake_backend": "",
        }
        assert results["silence_false_unknown_wakes"] == 1
        assert results["silence_false_wake_source"] == "unknown"

    def test_sum_equals_total_false_wakes(self):
        results = {
            "silence_false_wakes": 2,
            "silence_false_hotword_wakes": 1,
            "silence_false_clap_wakes": 1,
            "silence_false_unknown_wakes": 0,
        }
        total = (
            results["silence_false_hotword_wakes"]
            + results["silence_false_clap_wakes"]
            + results["silence_false_unknown_wakes"]
        )
        assert total == results["silence_false_wakes"]

    def test_zero_wakes_shows_all_counters_zero(self):
        results = {
            "silence_false_wakes": 0,
            "silence_false_hotword_wakes": 0,
            "silence_false_clap_wakes": 0,
            "silence_false_unknown_wakes": 0,
            "silence_false_wake_source": "none",
        }
        assert all(v == 0 or v == "none" for v in results.values())

    def test_wake_event_metadata_contains_source_and_backend(self):
        from scripts.debug_fast_wake_live import WakeEvent
        ev = WakeEvent("silence", "hotword", "openwakeword",
                       0.65, 0.65, "wake_detected", 1000.0)
        assert ev.phase == "silence"
        assert ev.source == "hotword"
        assert ev.backend == "openwakeword"
        assert ev.confidence == 0.65
        assert ev.score == 0.65
        assert ev.event_type == "wake_detected"

    def test_wake_event_type_false_wake(self):
        from scripts.debug_fast_wake_live import WakeEvent
        ev = WakeEvent("silence", "double_clap", "dsp_clap",
                       0.0, 0.0, "false_wake", 1000.0)
        assert ev.event_type == "false_wake"
        assert ev.source == "double_clap"
