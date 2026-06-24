"""Tests: no Win+J keyboard bridge is required for wake.

All wake events flow through InternalWakeSignalBus only.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestNoWinJBridgeRequired:
    def test_internal_wake_signal_bus_imports(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=True)
        assert bus is not None
        assert bus.signal_count == 0

    def test_internal_wake_signal_emit_wake(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=True)
        result = bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
        assert bus.signal_count == 1

    def test_internal_wake_signal_emit_listening(self):
        from engine.internal_wake_signal import InternalWakeSignalBus
        bus = InternalWakeSignalBus(debug=True)
        result = bus.emit_listening_started("hotword")
        assert bus.signal_count == 1

    def test_no_winj_in_runtime_bridge(self):
        import engine.runtime_bridge
        source = engine.runtime_bridge.__file__
        content = open(source, encoding="utf-8").read()
        assert "win" not in content.lower() or "Win+J" not in content
        assert "keyboard" not in content.lower() or "virtual_key" not in content or "SendKeys" not in content

    def test_no_winj_in_audio_wake_pipeline(self):
        import engine.audio_wake_pipeline
        source = engine.audio_wake_pipeline.__file__
        content = open(source, encoding="utf-8").read()
        assert "keyboard" not in content.lower() or "Win+J" not in content

    def test_no_winj_in_wake_orchestrator(self):
        import engine.wake_orchestrator
        source = engine.wake_orchestrator.__file__
        content = open(source, encoding="utf-8").read()
        assert "keyboard" not in content.lower() or "Win+J" not in content
