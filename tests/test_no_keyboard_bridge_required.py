from __future__ import annotations

from engine.internal_wake_signal import InternalWakeSignalBus


def test_internal_wake_signal_bus_does_not_use_keyboard():
    bus = InternalWakeSignalBus()
    assert hasattr(bus, "_queue")
    assert hasattr(bus, "_post_fn")
    assert not hasattr(bus, "_keyboard")
    assert not hasattr(bus, "_pynput")


def test_internal_wake_signal_bus_works_without_queue():
    """The bus should work even when no queue is set (no-op mode)."""
    bus = InternalWakeSignalBus()
    from engine.internal_wake_signal import WakeSignal
    result = bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    assert result is False  # No queue, no post_fn


def test_internal_wake_signal_bus_set_queue():
    bus = InternalWakeSignalBus()
    assert bus._queue is None
    bus.set_queue(object())
    assert bus._queue is not None
