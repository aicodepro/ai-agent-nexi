import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tone_manager_selects_expected_tones():
    from engine.tone_manager import Tone, ToneContext, ToneManager

    assert ToneManager.select_tone(ToneContext(handler_reason="tool")).mode == Tone.FOCUSED
    assert ToneManager.select_tone(ToneContext(route="clarify", confidence=0.4)).mode == Tone.LOW_CONFIDENCE
    assert ToneManager.select_tone(ToneContext(is_error=True)).mode == Tone.URGENT
    assert ToneManager.select_tone(ToneContext(route="system", is_greeting=True)).mode == Tone.FRIENDLY


def test_tone_manager_wraps_low_confidence_response():
    from engine.tone_manager import Tone, ToneManager
    tone = ToneManager.TONE_MAP[Tone.LOW_CONFIDENCE]
    assert ToneManager.wrap_response("You asked for search.", tone).startswith("I think ")


def test_tone_updates_presence_state():
    from engine.presence_state import get_presence_state, reset_presence_state
    from engine.tone_manager import ToneContext, ToneManager
    reset_presence_state()
    ToneManager.select_tone(ToneContext(handler_reason="react"))
    assert get_presence_state()["tone"] == "focused"
