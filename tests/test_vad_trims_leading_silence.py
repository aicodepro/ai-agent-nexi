"""Don't upload dead air to the ASR.

The capture loop appended every frame from listen-start, so a user who paused
before speaking got all that silence posted to Groq. Measured from a real run:
duration_ms=11600 for speech_ms=960 -> 371,244 bytes uploaded (16kHz*2*11.6s).
The ASR round-trip is dominated by upload size, so that was seconds of pure
latency per turn.

Trim the lead-in, but keep VAD_PREROLL_MS so the first phoneme is never clipped.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class _FakeVAD:
    """is_speech() true only for frames whose bytes are the speech marker."""

    def __init__(self, marker: bytes):
        self.marker = marker

    def is_speech(self, frame: bytes) -> bool:
        return frame == self.marker

    def reset(self):
        pass


SPEECH_MARKER = b"\x11" * 1280


@pytest.fixture
def pipeline(monkeypatch):
    from collections import deque

    from engine import audio_wake_pipeline as awp

    # capture_command() builds its own VAD via build_vad() — swap in the fake.
    monkeypatch.setattr(awp, "build_vad", lambda *_a, **_k: _FakeVAD(SPEECH_MARKER))

    pipe = awp.AudioWakePipeline.__new__(awp.AudioWakePipeline)  # no audio device
    pipe._preroll = deque(maxlen=5)          # 5 frames of lead-in
    pipe._vad = _FakeVAD(SPEECH_MARKER)
    pipe._last_capture_stats = {}
    pipe._post_status = lambda *_a, **_k: None
    return pipe


def _run(pipe, frames):
    """Drive capture_command's frame_source with a scripted frame list."""
    it = iter(frames)
    return pipe.capture_command(lambda: next(it, None), source="test")


def test_leading_silence_is_trimmed_but_preroll_is_kept(pipeline):
    SIL, SPEECH = b"\x00" * 1280, b"\x11" * 1280
    # 40 frames of silence (user thinking), 4 of speech, then trailing silence to end
    frames = [SIL] * 40 + [SPEECH] * 4 + [SIL] * 40
    audio = _run(pipeline, frames)

    kept = len(audio) // 1280
    assert audio.count(SPEECH) == 4, "speech frames must never be dropped"
    # trimmed well below the 84 captured frames, but NOT below the ASR minimum
    assert kept < 40, f"leading silence was not trimmed (kept {kept} frames)"
    assert audio.startswith(SIL), "should keep some silent lead-in (preroll)"
    # first speech frame must never sit at index 0 (that would clip the phoneme)
    first_speech = audio.find(SPEECH) // 1280
    assert first_speech > 0, "first phoneme was clipped — no preroll retained"


def test_trim_never_cuts_below_the_asr_minimum(pipeline):
    """REGRESSION (seen live): trimming made short utterances shorter than
    ASR_MIN_AUDIO_MS (1800ms), and the caller rejects those as
    "[COMMAND_CAPTURE] no_speech_timeout reached" -> listening -> thinking -> sleep.
    Darsh's log: speech_ms=400/duration=1600 died; only >=1840ms survived.
    The trim must keep extra lead-in rather than emit a too-short clip."""
    from engine import audio_wake_pipeline as awp

    SIL, SPEECH = b"\x00" * 1280, SPEECH_MARKER
    # long think-pause, then a SHORT utterance (5 frames = 400ms of speech)
    frames = [SIL] * 40 + [SPEECH] * 5 + [SIL] * 40
    audio = _run(pipeline, frames)

    kept_ms = (len(audio) // 1280) * 80
    assert kept_ms >= awp.ASR_MIN_AUDIO_MS, (
        f"trimmed to {kept_ms}ms, below ASR_MIN_AUDIO_MS={awp.ASR_MIN_AUDIO_MS} — the caller "
        f"would discard this as no_speech_timeout"
    )
    assert audio.count(SPEECH) == 5, "speech must still be intact"


def test_no_speech_at_all_is_not_broken_by_trimming(pipeline):
    SIL, SPEECH = b"\x00" * 1280, b"\x11" * 1280
    audio = _run(pipeline, [SIL] * 60)
    assert isinstance(audio, bytes)  # must not raise when speech never started


def test_capture_stats_reflect_the_trimmed_audio(pipeline):
    SIL, SPEECH = b"\x00" * 1280, b"\x11" * 1280
    frames = [SIL] * 40 + [SPEECH] * 4 + [SIL] * 40
    audio = _run(pipeline, frames)
    stats = pipeline._last_capture_stats
    # duration must describe what we actually send, or the ASR gate reasons about
    # audio that no longer exists
    assert stats["duration_ms"] == (len(audio) // 1280) * 80
    assert stats["speech_ms"] == 4 * 80
