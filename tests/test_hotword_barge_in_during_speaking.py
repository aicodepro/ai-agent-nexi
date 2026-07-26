#!/usr/bin/env python3
"""Hotword barge-in while Nexi is speaking.

Contract (engine/audio_wake_pipeline.py::process_frame): a wake word detected
while _is_speaking() enqueues a barge-in request via runtime_bridge and returns
{"wake": False, "source": "hotword", "reason": "barge_in_requested"} -- it does
NOT emit a normal wake and does NOT call the old barge_in_manager.interrupt.
The wake score must clear the threshold; silence must NOT barge in (that is the
self-trigger guard), so these tests inject a scorer that returns a high score.
"""
import os
import queue
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.audio_wake_pipeline import AudioWakePipeline


class _HotwordScorer:
    name = "scripted"

    def score(self, frame):
        return 0.9  # above OPENWAKEWORD_SCORE_THRESHOLD default (0.35)


def _run_barge_in_frame():
    cmd_queue = queue.Queue()
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1") as mock_post:
        msm.return_value.is_global_tts_active.return_value = False
        msm.return_value.are_detectors_paused.return_value = True
        msm.return_value.get_state.return_value = "saying"
        msm.return_value.get_session_id.return_value = "sess-1"
        msm.return_value.get_session_epoch.return_value = 1

        pipeline = AudioWakePipeline(command_queue=cmd_queue, wake_scorer=_HotwordScorer())
        result = pipeline.process_frame(b"\x10\x00" * 160)
        return result, mock_post


def test_hotword_barge_in_during_speaking_requests_barge_in():
    result, mock_post = _run_barge_in_frame()
    assert mock_post.called, "a barge-in request must be enqueued"
    assert result["source"] == "hotword"
    assert result["reason"] == "barge_in_requested"
    # It is a barge-in, not a normal wake capture.
    assert result["wake"] is False


def test_barge_in_works_while_the_global_tts_lease_is_held():
    """Regression: barge-in was unreachable in the real runtime.

    The two tests above set is_global_tts_active=False, but in production that
    flag is True on every frame while Nexi speaks - which is precisely when
    barge-in is needed. The global-TTS gate returned before the barge-in check,
    so the wake scorer never ran and a long answer could not be interrupted.
    """
    cmd_queue = queue.Queue()
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1") as mock_post:
        msm.return_value.is_global_tts_active.return_value = True   # the real state
        msm.return_value.are_detectors_paused.return_value = True   # also real
        msm.return_value.get_state.return_value = "saying"
        msm.return_value.get_session_id.return_value = "sess-1"
        msm.return_value.get_session_epoch.return_value = 1

        pipeline = AudioWakePipeline(command_queue=cmd_queue, wake_scorer=_HotwordScorer())
        result = pipeline.process_frame(b"\x10\x00" * 160)

    assert result["reason"] != "global_tts_active", \
        "the TTS gate ran before barge-in, making interruption impossible"
    assert mock_post.called, "a barge-in request must be enqueued while TTS holds the lease"
    assert result["reason"] == "barge_in_requested"


def test_tts_lease_still_suppresses_capture_when_not_speaking():
    """The gate must survive the reorder: audio owned by a TTS lease elsewhere
    must not be captured as a command just because this process isn't speaking."""
    cmd_queue = queue.Queue()
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=False):
        msm.return_value.is_global_tts_active.return_value = True
        msm.return_value.are_detectors_paused.return_value = False
        pipeline = AudioWakePipeline(command_queue=cmd_queue, wake_scorer=_HotwordScorer())
        result = pipeline.process_frame(b"\x10\x00" * 160)

    assert result["reason"] == "global_tts_active"
    assert result["wake"] is False


def test_hotword_barge_in_during_speaking_echo_guard():
    # Silence (no scorer hit) must NOT barge in -- this is what stops Nexi's own
    # TTS from waking itself.
    cmd_queue = queue.Queue()

    class _SilentScorer:
        name = "scripted"

        def score(self, frame):
            return 0.0

    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1") as mock_post:
        msm.return_value.is_global_tts_active.return_value = False
        msm.return_value.get_session_id.return_value = "sess-1"
        msm.return_value.get_session_epoch.return_value = 1
        pipeline = AudioWakePipeline(command_queue=cmd_queue, wake_scorer=_SilentScorer())
        result = pipeline.process_frame(b"\x00\x00" * 160)

    assert not mock_post.called, "silence must not trigger a barge-in (echo guard)"
    assert result["reason"] == "speaking"
    assert result["wake"] is False
