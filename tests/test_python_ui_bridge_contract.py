from __future__ import annotations

from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_all_contract_states_emittable():
    """All required UI bridge states must be emittable."""
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    bus.emit_waiting_for_speech("hotword")
    bus.emit_transcript("test", "voice")
    bus.emit_assistant_response("response")
    bus.emit_tts_started()
    bus.emit_tts_done()
    bus.emit_no_speech("hotword")
    states = {s.state for s in signals}
    required = {"wake_detected", "listening", "waiting_for_speech", "asr_result",
                 "assistant_response", "saying", "sleep", "no_speech"}
    missing = required - states
    assert not missing, f"Missing states: {missing}"


def test_bridge_contract_state_order():
    """Wake → Listening → Waiting → Transcript must be in order."""
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    bus.emit_waiting_for_speech("hotword")
    bus.emit_transcript("test", "voice")
    order = [s.state for s in signals]
    assert order.index("wake_detected") < order.index("listening")
    assert order.index("listening") < order.index("waiting_for_speech")


def test_bridge_contract_no_invalid_states():
    signals = []
    bus = InternalWakeSignalBus(post_fn=lambda s: signals.append(s))
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_listening_started("hotword")
    valid_states = {"wake_detected", "listening", "waiting_for_speech", "asr_result",
                     "assistant_response", "saying", "sleep", "no_speech", "recognising"}
    for s in signals:
        assert s.state in valid_states, f"Invalid state: {s.state}"
