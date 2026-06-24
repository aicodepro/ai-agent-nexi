from __future__ import annotations

from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_wake_signal_triggers_listening_after_wake():
    """After a wake_detected signal, emit_listening_started should be called."""
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected", confidence=0.9))
    assert len(signals) == 1
    assert signals[0].state == "wake_detected"

    bus.emit_listening_started("hotword")
    assert len(signals) == 2
    assert signals[1].state == "listening"
    assert signals[1].source == "hotword"


def test_listening_emitted_immediately_after_wake():
    """No delay should separate wake_detected and listening."""
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
    bus.emit_listening_started("double_clap")
    assert signals[0].state == "wake_detected"
    assert signals[1].state == "listening"
    assert abs(signals[1].timestamp - signals[0].timestamp) < 0.1
