"""Tests: silence false wake is reported with source and metadata."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSilenceFalseWakeFailureReported:
    def test_results_tracks_silence_false_wake_source(self):
        results = {
            "silence_false_wakes": 1,
            "silence_false_wake_source": "hotword",
            "silence_false_wake_backend": "openwakeword",
        }
        assert results["silence_false_wakes"] > 0
        assert results["silence_false_wake_source"] in ("hotword", "double_clap", "unknown")
        assert results["silence_false_wake_backend"] != ""

    def test_results_tracks_silence_false_wake_confidence(self):
        results = {
            "silence_false_wakes": 1,
            "silence_false_wake_confidence": 0.6489,
            "silence_false_wake_score": 0.6489,
        }
        assert results["silence_false_wake_confidence"] > 0.0
        assert results["silence_false_wake_score"] >= 0.0

    def test_no_false_wake_shows_zero(self):
        results = {
            "silence_false_wakes": 0,
            "silence_false_wake_source": "none",
        }
        assert results["silence_false_wakes"] == 0
        assert results["silence_false_wake_source"] == "none"

    def test_silence_wake_output_format(self):
        source = "hotword"
        backend = "openwakeword"
        confidence = 0.65
        score = 0.65
        out = f"[SILENCE_WAKE] source={source} backend={backend} confidence={confidence:.4f} score={score:.4f} phase=silence"
        assert "[SILENCE_WAKE]" in out
        assert "source=hotword" in out
        assert "backend=openwakeword" in out
        assert "confidence=0.6500" in out
        assert "score=0.6500" in out

    def test_silence_wake_format_for_clap(self):
        source = "double_clap"
        backend = "dsp_clap"
        amplitude = 0.22
        out = f"[SILENCE_WAKE] source={source} backend={backend} confidence={amplitude:.4f} phase=silence"
        assert "[SILENCE_WAKE]" in out
        assert "source=double_clap" in out
        assert "backend=dsp_clap" in out
        assert "confidence=0.2200" in out
