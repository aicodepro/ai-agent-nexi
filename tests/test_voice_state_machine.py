import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


@pytest.fixture(autouse=True)
def _fresh():
    from engine.voice_state_machine import get_voice_state_machine
    get_voice_state_machine().reset()
    yield
    get_voice_state_machine().reset()


def test_happy_path_transitions():
    from engine.voice_state_machine import get_voice_state_machine
    import engine.voice_state_machine as vsm
    m = get_voice_state_machine()
    assert m.get_state() == vsm.SLEEPING
    assert m.transition("wake_detected") == vsm.LISTENING
    assert m.transition("speech_started") == vsm.RECORDING_UTTERANCE
    assert m.transition("asr_started") == vsm.RECOGNIZING
    assert m.transition("command_started") == vsm.THINKING
    assert m.transition("tts_started") == vsm.SPEAKING
    assert m.transition("tts_finished") == vsm.COOLDOWN
    assert m.transition("cooldown_complete") == vsm.SLEEPING


def test_full_command_gate():
    from engine.voice_state_machine import get_voice_state_machine
    m = get_voice_state_machine()
    m.transition("wake_detected")
    assert m.can_accept_full_command() is True
    m.transition("speech_started")
    assert m.can_accept_full_command() is True
    m.transition("asr_started")
    assert m.can_accept_full_command() is False  # RECOGNIZING
    m.transition("command_started")
    assert m.can_accept_full_command() is False  # THINKING
    m.transition("tts_started")
    assert m.can_accept_full_command() is False  # SPEAKING


def test_interrupt_only_during_speaking():
    from engine.voice_state_machine import get_voice_state_machine
    m = get_voice_state_machine()
    m.transition("wake_detected")
    assert m.can_accept_interrupt() is False
    m.transition("speech_started")
    m.transition("asr_started")
    m.transition("command_started")
    m.transition("tts_started")
    assert m.can_accept_interrupt() is True
    assert m.is_interrupt_word("stop") is True
    assert m.is_interrupt_word("please stop talking") is True
    assert m.is_interrupt_word("open chrome") is False


def test_any_to_sleeping_on_sleep_or_error():
    from engine.voice_state_machine import get_voice_state_machine
    import engine.voice_state_machine as vsm
    m = get_voice_state_machine()
    m.transition("wake_detected")
    m.transition("speech_started")
    assert m.transition("sleep") == vsm.SLEEPING
    m.transition("wake_detected")
    assert m.transition("error") == vsm.ERROR
    assert m.transition("session_finish") == vsm.SLEEPING


def test_unknown_event_is_noop():
    from engine.voice_state_machine import get_voice_state_machine
    m = get_voice_state_machine()
    m.transition("wake_detected")
    before = m.get_state()
    assert m.transition("not_a_real_event") == before
