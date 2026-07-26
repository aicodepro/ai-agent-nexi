"""One barge-in must produce exactly one interrupt transaction.

Live trace:
    [BARGE_IN] hotword_during_speaking score=0.997
    ... TTS still winding down ...
    [BARGE_IN] transaction_expired id=eac64372
    [BARGE_IN] hotword_during_speaking score=0.996   <- SECOND transaction

_expire_pending_barge_in() cleared _pending_barge_in on a fixed deadline even
while TTS had not acknowledged the stop. Clearing it removed the only thing
rejecting further candidates, so the tail of the same utterance opened another
interrupt.
"""
from __future__ import annotations

import queue
import time
from unittest.mock import patch

import pytest

from engine.audio_wake_pipeline import AudioWakePipeline
import engine.audio_wake_pipeline as awp


class _HotwordScorer:
    name = "scripted"

    def score(self, frame):
        return 0.99


FRAME = b"\x10\x00" * 160


def _pipeline_speaking(msm, *, tts_active=True):
    msm.return_value.is_global_tts_active.return_value = True
    msm.return_value.are_detectors_paused.return_value = True
    msm.return_value.get_state.return_value = "saying"
    msm.return_value.get_session_id.return_value = "sess-1"
    msm.return_value.get_session_epoch.return_value = 1
    msm.return_value.is_current.return_value = True
    msm.return_value.is_tts_active.return_value = tts_active
    msm.return_value.is_tts_cooldown_active.return_value = False
    return AudioWakePipeline(command_queue=queue.Queue(), wake_scorer=_HotwordScorer())


def test_second_candidate_is_rejected_while_transaction_is_open():
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1") as post:
        p = _pipeline_speaking(msm)
        first = p.process_frame(FRAME)
        assert first["reason"] == "barge_in_requested"

        for _ in range(5):
            again = p.process_frame(FRAME)
            assert again["reason"] == "barge_in_pending"
        assert post.call_count == 1, "a second interrupt was requested"


def test_transaction_does_not_expire_while_tts_is_still_stopping():
    """The exact defect: expiry mid-stop unblocked the next candidate."""
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1"):
        p = _pipeline_speaking(msm, tts_active=True)
        p.process_frame(FRAME)

        p._pending_barge_in["deadline"] = time.time() - 1.0  # soft deadline passed
        assert p._expire_pending_barge_in() is False, "expired before TTS acknowledged"
        assert p._pending_barge_in is not None, "the guard against a 2nd interrupt was dropped"


def test_hard_deadline_still_releases_a_stuck_transaction():
    """Renewal must be bounded - a stuck TTS producer cannot pin it forever."""
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-1"), \
         patch("engine.audio_wake_pipeline.finish_session"):
        p = _pipeline_speaking(msm, tts_active=True)
        p.process_frame(FRAME)

        now = time.time()
        p._pending_barge_in["deadline"] = now - 1.0
        p._pending_barge_in["hard_deadline"] = now - 0.5
        assert p._expire_pending_barge_in() is True
        assert p._pending_barge_in is None


def test_expiry_starts_a_refractory_window():
    """After a transaction closes, the tail of the same utterance must not
    immediately open the next one."""
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-2") as post, \
         patch("engine.audio_wake_pipeline.finish_session"):
        p = _pipeline_speaking(msm, tts_active=False)
        p.process_frame(FRAME)
        assert post.call_count == 1

        now = time.time()
        p._pending_barge_in["deadline"] = now - 1.0
        p._pending_barge_in["hard_deadline"] = now - 0.5
        assert p._expire_pending_barge_in() is True

        for _ in range(5):
            result = p.process_frame(FRAME)
            assert result["reason"] == "barge_in_refractory"
        assert post.call_count == 1, "a second transaction opened after expiry"


def test_refractory_is_bounded_so_real_barge_in_still_works():
    assert awp._BARGE_IN_REFRACTORY_SECONDS <= 5.0, "refractory would block real barge-in"
    assert awp._BARGE_IN_HARD_TIMEOUT_SECONDS >= awp._BARGE_IN_TRANSACTION_TIMEOUT_SECONDS


def test_a_later_genuine_barge_in_is_still_accepted():
    """After the refractory passes, a real interruption must work again."""
    with patch("engine.audio_wake_pipeline.get_session_manager") as msm, \
         patch("engine.audio_wake_pipeline._is_speaking", return_value=True), \
         patch("engine.runtime_bridge.post_barge_in_request", return_value="req-3") as post, \
         patch("engine.audio_wake_pipeline.finish_session"):
        p = _pipeline_speaking(msm, tts_active=False)
        p.process_frame(FRAME)
        now = time.time()
        p._pending_barge_in["deadline"] = now - 1.0
        p._pending_barge_in["hard_deadline"] = now - 0.5
        p._expire_pending_barge_in()

        p._barge_in_refractory_until = time.time() - 0.01  # window elapsed
        result = p.process_frame(FRAME)
        assert result["reason"] == "barge_in_requested"
        assert post.call_count == 2
