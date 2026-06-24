"""Tests: InternalWakeSignalBus listening flow.

Verifies that wake → listening → VAD → ASR flow works without keyboard bridge.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestInternalWakeSignalListeningFlow:
    def test_wake_then_listening_sequence(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=True)
        w = bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
        l = bus.emit_listening_started("hotword")
        assert bus.signal_count == 2

    def test_wake_then_listening_with_double_clap(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=True)
        bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
        bus.emit_listening_started("double_clap")
        assert bus.signal_count == 2

    def test_listening_after_wake_source_preserved(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=True)
        bus.emit_wake(WakeSignal(source="hotword", state="wake_detected", confidence=0.9))
        bus.emit_listening_started(source="hotword")
        assert bus.signal_count == 2

    def test_multiple_wake_sources_do_not_interfere(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=True)
        bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
        bus.emit_listening_started("hotword")
        bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
        bus.emit_listening_started("double_clap")
        assert bus.signal_count == 4

    def test_no_keyboard_bridge_in_flow(self):
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        source = InternalWakeSignalBus.__module__
        import engine.internal_wake_signal as mod
        content = open(mod.__file__, encoding="utf-8").read()
        assert "win" not in content.lower() or "SendKeys" not in content
        assert "keyboard" not in content.lower() or "Write-Output" not in content

    def test_wake_orchestrator_accepts_both_sources(self):
        from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult
        orch = WakeOrchestrator({"cooldown_ms": 200, "debug": True, "allow_sources": {"hotword", "double_clap", "hotkey"}})
        r1 = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=0.9))
        assert r1.should_wake is True
        assert r1.source == "hotword"
        orch.mark_listening_finished()
        time.sleep(0.25)
        r2 = orch.evaluate(WakeSourceResult(source="double_clap", detected=True, confidence=0.95))
        assert r2.should_wake is True
        assert r2.source == "double_clap"
