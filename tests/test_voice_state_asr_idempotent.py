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
