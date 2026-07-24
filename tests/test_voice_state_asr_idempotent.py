import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.voice_state_machine import VoiceStateMachine, VoiceState


def test_asr_started_idempotent_in_recognizing():
    sm = VoiceStateMachine()
    sm.reset()
    sm.transition("wake_detected")   # SLEEPING -> LISTENING
    sm.transition("asr_started")     # LISTENING -> RECOGNIZING
    assert sm.get_voice_state() == VoiceState.RECOGNIZING
    # Duplicate asr_started must stay in RECOGNIZING (no transition_failed spam).
    sm.transition("asr_started")
    assert sm.get_voice_state() == VoiceState.RECOGNIZING
    sm.transition("asr_started")
    assert sm.get_voice_state() == VoiceState.RECOGNIZING


def test_listening_started_rearms_after_question_while_speaking():
    # Assistant asks a question (clarify/approval) -> auto-listen fires listening_started
    # while TTS is still SPEAKING; the mic must re-arm, not transition_failed.
    sm = VoiceStateMachine()
    sm.reset()
    sm.transition("wake_detected")
    sm.transition("command_started")     # -> THINKING
    sm.transition("tts_started")         # -> SPEAKING (asking the question)
    assert sm.get_voice_state() == VoiceState.SPEAKING
    sm.transition("listening_started", source="assistant_question")
    assert sm.get_voice_state() == VoiceState.LISTENING


def test_listening_started_rearms_from_sleeping_and_thinking():
    sm = VoiceStateMachine()
    sm.reset()
    assert sm.get_voice_state() == VoiceState.SLEEPING
    sm.transition("listening_started", source="assistant_question")
    assert sm.get_voice_state() == VoiceState.LISTENING
