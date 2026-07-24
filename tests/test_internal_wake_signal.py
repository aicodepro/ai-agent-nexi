from __future__ import annotations

import time
from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_internal_wake_signal_bus_emits_wake():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected", confidence=0.9))
    assert len(signals) == 1
    assert signals[0].source == "hotword"
    assert signals[0].confidence == 0.9


def test_internal_wake_signal_bus_emits_listening():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_listening_started("hotword")
    assert len(signals) == 1
    assert signals[0].state == "listening"


def test_internal_wake_signal_bus_emits_waiting():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_waiting_for_speech("hotword")
    assert len(signals) == 1
    assert signals[0].state == "waiting_for_speech"


def test_internal_wake_signal_bus_emits_transcript():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_transcript("hello world", "voice")
    assert len(signals) == 1
    assert signals[0].state == "asr_result"
    assert signals[0].text == "hello world"


def test_internal_wake_signal_bus_emits_tts():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_tts_started()
    bus.emit_tts_done()
    assert len(signals) == 2
    assert signals[0].state == "saying"
    assert signals[1].state == "sleep"


def test_internal_wake_signal_bus_signal_count():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    assert bus.signal_count == 0
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    assert bus.signal_count == 1
    bus.emit_wake(WakeSignal(source="clap", state="wake_detected"))
    assert bus.signal_count == 2
