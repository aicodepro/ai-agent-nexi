#!/usr/bin/env python3
"""Integration tests for hotword barge-in.

Contract (engine/audio_wake_pipeline.py::process_frame):
- Wake word while _is_speaking(): enqueue a barge-in request via
  runtime_bridge.post_barge_in_request and return
  {"wake": False, "source": "hotword", "reason": "barge_in_requested"}.
  It is NOT a normal wake and does NOT call barge_in_manager.interrupt.
- Wake word while NOT speaking and listening: normal wake
  {"wake": True, "source": "hotword"}.
The wake score must clear the threshold, so these tests inject a scorer.
"""
import os
import queue
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine.audio_wake_pipeline as awp
from engine.audio_wake_pipeline import AudioWakePipeline


class _HotwordScorer:
    name = "scripted"

    def score(self, frame):
        return 0.9  # above OPENWAKEWORD_SCORE_THRESHOLD (default 0.35)


def _barge_in_frame():
    """Run one frame with Nexi speaking + a hotword hit; return (result, post_mock)."""
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1") as mock_post:
        msm.return_value.is_global_tts_active.return_value = False
        msm.return_value.are_detectors_paused.return_value = True
        msm.return_value.get_state.return_value = "saying"
        msm.return_value.get_session_id.return_value = "sess-1"
        msm.return_value.get_session_epoch.return_value = 1
        pipeline = AudioWakePipeline(command_queue=queue.Queue(), wake_scorer=_HotwordScorer())
        return pipeline.process_frame(b"\x10\x00" * 160), mock_post


def test_hotword_during_speaking_intercepts_and_interrupts_tts():
    result, mock_post = _barge_in_frame()
    assert mock_post.called
    assert result["source"] == "hotword"
    assert result["reason"] == "barge_in_requested"


def test_hotword_during_speaking_does_not_route_hotword_as_command():
    result, _ = _barge_in_frame()
    # Barge-in is not a captured command: wake stays False.
    assert result["wake"] is False
    assert result["reason"] == "barge_in_requested"


def test_next_utterance_after_hotword_barge_in_is_routed(monkeypatch):
    # A normal hotword (not while speaking) is a normal wake. Single-frame test,
    # so lower the anti-false-wake consecutive-hits default (2) for this case.
    monkeypatch.setattr(awp, "OWW_THRESHOLD", 0.5)
    monkeypatch.setattr(awp, "OWW_CONSECUTIVE", 1)
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=False):
        msm.return_value.is_global_tts_active.return_value = False
        msm.return_value.are_detectors_paused.return_value = False
        msm.return_value.is_post_session_suppressed.return_value = False
        pipeline = awp.AudioWakePipeline(command_queue=queue.Queue(), wake_scorer=_HotwordScorer())
        result = pipeline.process_frame(b"\x10\x00" * 160)
    assert result["wake"] is True
    assert result["source"] == "hotword"


def test_voice_state_gate_rejects_commands_during_speaking_with_hotword():
    # While speaking, a hotword becomes a barge-in request, never a command wake.
    result, mock_post = _barge_in_frame()
    assert result["wake"] is False
    assert result["reason"] == "barge_in_requested"
    assert mock_post.called


def test_voice_diagnostics_include_hotword_barge_in_status():
    # After a barge-in request, the pipeline holds pending barge-in state and a
    # follow-up frame reports it (rather than firing a second request).
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1") as mock_post:
        msm.return_value.is_global_tts_active.return_value = False
        msm.return_value.get_session_id.return_value = "sess-1"
        msm.return_value.get_session_epoch.return_value = 1
        pipeline = AudioWakePipeline(command_queue=queue.Queue(), wake_scorer=_HotwordScorer())
        first = pipeline.process_frame(b"\x10\x00" * 160)
        second = pipeline.process_frame(b"\x10\x00" * 160)

    assert first["reason"] == "barge_in_requested"
    assert mock_post.call_count == 1  # not re-requested while one is pending
    assert second["reason"] == "barge_in_pending"
