"""Speech that never started cannot have "ended".

Live trace:
    [VAD] speech_ended duration_ms=4000 speech_ms=0
    [VOICE_STATE] transition_failed reason=no_valid_transition
                  event=speech_ended current=listening
    [UI_SEND] state=recognising label=RECOGNISING

The capture ended with speech_ms=0, but the pipeline still posted
"speech_ended". There is no (LISTENING, speech_ended) transition, so the state
machine rejected it - and the UI announced "Recognising speech..." when no
speech existed, which is actively misleading for a screen-reader user.
"""
from __future__ import annotations

import pytest

from engine.voice_state_machine import VoiceState, VoiceStateMachine
from engine.ui_state_manager import STATE_ALIASES


def _machine_listening() -> VoiceStateMachine:
    m = VoiceStateMachine()
    m.transition("wake_detected", source="hotword")
    m.transition("listening_started", source="hotword")
    assert m.get_voice_state() is VoiceState.LISTENING
    return m


def test_no_speech_timeout_is_a_valid_transition_from_listening(capsys):
    m = _machine_listening()
    m.transition("no_speech_timeout", source="hotword")

    out = capsys.readouterr().out
    assert "no_valid_transition" not in out, "no-speech still produced an invalid transition"
    assert m.get_voice_state() is VoiceState.LISTENING


def test_speech_ended_from_listening_is_still_invalid():
    """The guard must stay: 'ended' without 'started' is a contradiction."""
    m = _machine_listening()
    m.transition("speech_ended", source="hotword")
    assert m.get_voice_state() is VoiceState.LISTENING, \
        "speech_ended from LISTENING must not advance the machine"


def test_real_speech_still_reaches_recognizing():
    m = _machine_listening()
    m.transition("speech_started", source="hotword")
    assert m.get_voice_state() is VoiceState.RECORDING_UTTERANCE
    m.transition("speech_ended", source="hotword")
    assert m.get_voice_state() is VoiceState.RECOGNIZING


def test_no_speech_after_real_speech_still_recognizes():
    """A capture that had speech but timed out still has audio to transcribe."""
    m = _machine_listening()
    m.transition("speech_started", source="hotword")
    m.transition("no_speech_timeout", source="hotword")
    assert m.get_voice_state() is VoiceState.RECOGNIZING


def test_no_speech_does_not_announce_recognising():
    """Announcing 'Recognising speech' with no speech misleads a blind user."""
    assert STATE_ALIASES.get("no_speech_timeout") != "recognising"
    assert STATE_ALIASES.get("no_speech_timeout") == "listening"
    assert STATE_ALIASES.get("speech_ended") == "recognising"


def test_pipeline_emits_no_speech_timeout_when_speech_never_started():
    """The emitter side: the status must depend on whether speech started."""
    import inspect
    from engine import audio_wake_pipeline

    src = inspect.getsource(audio_wake_pipeline)
    assert '"speech_ended" if speech_started else "no_speech_timeout"' in src, \
        "the pipeline still posts speech_ended unconditionally"
