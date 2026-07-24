from __future__ import annotations

from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_combined_sources_emit_separate_signals():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    bus.emit_waiting_for_speech("hotword")
    bus.emit_no_speech("hotword")
    assert len(signals) == 4
    bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
    bus.emit_listening_started("double_clap")
    bus.emit_waiting_for_speech("double_clap")
    bus.emit_transcript("test", "double_clap")
    assert len(signals) == 8
    sources = [s.source for s in signals]
    assert "hotword" in sources
    assert "double_clap" in sources


def test_wake_signals_include_timestamp():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected", timestamp=100.0))
    assert signals[0].timestamp > 0
    assert isinstance(signals[0].timestamp, float)


def test_signal_flow_hotword():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    bus.emit_waiting_for_speech("hotword")
    bus.emit_transcript("hello world", "voice")
    expected = ["wake_detected", "listening", "waiting_for_speech", "asr_result"]
    assert [s.state for s in signals] == expected


def test_signal_flow_clap():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
    bus.emit_listening_started("double_clap")
    bus.emit_waiting_for_speech("double_clap")
    bus.emit_transcript("turn on lights", "voice")
    expected = ["wake_detected", "listening", "waiting_for_speech", "asr_result"]
    assert [s.state for s in signals] == expected
