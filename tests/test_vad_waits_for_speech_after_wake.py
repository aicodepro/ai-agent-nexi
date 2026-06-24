from __future__ import annotations

from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_waiting_for_speech_emitted_after_listening():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    bus.emit_waiting_for_speech("hotword")
    assert len(signals) == 3
    assert signals[2].state == "waiting_for_speech"


def test_waiting_for_speech_has_correct_source():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_waiting_for_speech("double_clap")
    assert signals[0].source == "double_clap"
