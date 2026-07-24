"""Test combined custom hotword + CLAP_NN runtime integration.

Verifies that both wake sources (hotword + double clap) coexist
correctly through the shared InternalWakeSignalBus and WakeOrchestrator.
"""

import struct
import time


def test_hotword_and_double_clap_can_coexist():
    """Both hotword engine and clap backend manager can be created."""
    from engine.hotword_engine_manager import HotwordEngineManager
    from engine.clap_backend_manager import ClapBackendManager

    hw = HotwordEngineManager({"enabled": False})
    clap = ClapBackendManager(cooldown_ms=0)

    assert hasattr(hw, "process_audio_chunk")
    assert hasattr(clap, "process_audio_chunk")
    assert clap.primary_name in ("clap_nn", "dsp_clap")


def test_wake_orchestrator_accepts_hotword():
    """WakeOrchestrator can evaluate a hotword signal."""
    from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult

    wo = WakeOrchestrator({"cooldown_ms": 500})
    result = wo.evaluate(WakeSourceResult(source="hotword", detected=True,
                                           confidence=0.9))
    assert isinstance(result.should_wake, bool)


def test_wake_orchestrator_accepts_double_clap():
    """WakeOrchestrator can evaluate a double clap signal."""
    from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult

    wo = WakeOrchestrator({"cooldown_ms": 500})
    result = wo.evaluate(WakeSourceResult(source="double_clap", detected=True,
                                           confidence=0.95))
    assert isinstance(result.should_wake, bool)


def test_hotword_and_clap_share_cooldown():
    """If wake recently triggered, both sources should be suppressed."""
    from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult

    wo = WakeOrchestrator({"cooldown_ms": 5000})
    r1 = wo.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=0.9))

    r2 = wo.evaluate(WakeSourceResult(source="double_clap", detected=True, confidence=0.95))
    assert not r2.should_wake, "Double clap should be suppressed by hotword cooldown"


def test_internal_wake_signal_bridge():
    """InternalWakeSignalBus can emit both wake and listening signals."""
    from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal

    bus = InternalWakeSignalBus()
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    bus.emit_wake(WakeSignal(source="double_clap", state="wake_detected"))
    bus.emit_listening_started(source="hotword")
    assert True


def test_clap_nn_no_wake_on_speech_after_hotword():
    """Speech after hotword must not trigger clap wake."""
    from engine.clap_backend_manager import ClapBackendManager

    class FakeClapBackend:
        def process_pcm16(self, data, ts):
            from engine.clap_nn_backend import ClapNNResult
            return ClapNNResult(is_clap=False, confidence=0.05, timestamp=ts,
                                reason="speech_or_noise")

    m = ClapBackendManager(cooldown_ms=0)
    m._primary = FakeClapBackend()
    m._primary_ready = True
    m._primary_name = "clap_nn"
    m._min_gap_ms = 180
    m._max_gap_ms = 900

    for _ in range(5):
        frame = struct.pack("<1280h", *([0] * 1280))
        r = m.process_audio_chunk(frame)
        assert not r["wake"]


def test_runtime_bridge_has_wake_posting():
    """runtime_bridge must have post_wake_detected and status posting."""
    from engine import runtime_bridge
    assert hasattr(runtime_bridge, "post_wake_detected")
    assert hasattr(runtime_bridge, "post_status")
