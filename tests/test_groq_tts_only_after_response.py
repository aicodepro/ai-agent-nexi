from __future__ import annotations

from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_tts_only_emitted_after_assistant_response():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    bus.emit_waiting_for_speech("hotword")
    bus.emit_transcript("hello", "voice")
    bus.emit_assistant_response("Hello, how can I help?")
    bus.emit_tts_started()
    bus.emit_tts_done()
    states = [s.state for s in signals]
    assert "saying" in states
    assert "wake_detected" in states
    assert states.index("saying") > states.index("assistant_response")


def test_no_tts_before_wake():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_tts_started()
    assert signals[0].state == "saying"


def test_no_tts_on_error():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_no_speech("hotword")
    states = [s.state for s in signals]
    assert "saying" not in states
