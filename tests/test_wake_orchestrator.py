"""Tests for WakeOrchestrator (Phase 3)."""

import time
from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult, WakeDecision


def _clock_fake() -> float:
    return 1000.0


def test_evaluate_hotword_detected():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False})
    result = WakeSourceResult(source="hotword", detected=True, confidence=0.85, timestamp=_clock_fake())
    decision = orch.evaluate(result)
    assert decision.should_wake is True
    assert decision.source == "hotword"


def test_evaluate_double_clap_detected():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    result = WakeSourceResult(source="double_clap", detected=True, confidence=0.92, timestamp=_clock_fake())
    decision = orch.evaluate(result)
    assert decision.should_wake is True
    assert decision.source == "double_clap"


def test_evaluate_hotkey_detected():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    result = WakeSourceResult(source="hotkey", detected=True, confidence=1.0, timestamp=_clock_fake())
    decision = orch.evaluate(result)
    assert decision.should_wake is True
    assert decision.source == "hotkey"


def test_not_detected_no_wake():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False})
    result = WakeSourceResult(source="hotword", detected=False, confidence=0.02, timestamp=_clock_fake())
    decision = orch.evaluate(result)
    assert decision.should_wake is False


def test_suppress_while_listening():
    orch = WakeOrchestrator({"clock": _clock_fake, "suppress_while_listening": True, "debug": False})
    orch.mark_listening_started()
    result = WakeSourceResult(source="hotword", detected=True, confidence=0.85, timestamp=_clock_fake())
    decision = orch.evaluate(result)
    assert decision.should_wake is False
    assert decision.reason == "already_listening"


def test_listening_finished_allows_wake():
    orch = WakeOrchestrator({"clock": _clock_fake, "suppress_while_listening": True, "debug": False})
    orch.mark_listening_started()
    orch.mark_listening_finished()
    result = WakeSourceResult(source="hotword", detected=True, confidence=0.85, timestamp=_clock_fake())
    decision = orch.evaluate(result)
    assert decision.should_wake is True


def test_cooldown_blocks_duplicate():
    clock = [1000.0]
    def advancing_clock():
        val = clock[0]
        clock[0] += 0.5
        return val

    orch = WakeOrchestrator({"clock": advancing_clock, "cooldown_ms": 1800, "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    r1 = WakeSourceResult(source="hotword", detected=True, confidence=0.85, timestamp=clock[0])
    d1 = orch.evaluate(r1)
    assert d1.should_wake is True

    r2 = WakeSourceResult(source="double_clap", detected=True, confidence=0.92, timestamp=clock[0] + 0.5)
    d2 = orch.evaluate(r2)
    assert d2.should_wake is False
    assert d2.reason == "cooldown"


def test_cooldown_expires():
    clock = [1000.0]
    def advancing_clock():
        val = clock[0]
        clock[0] += 2.0
        return val

    orch = WakeOrchestrator({"clock": advancing_clock, "cooldown_ms": 1800, "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    r1 = WakeSourceResult(source="hotword", detected=True, confidence=0.85, timestamp=clock[0])
    assert orch.evaluate(r1).should_wake is True

    r2 = WakeSourceResult(source="double_clap", detected=True, confidence=0.92, timestamp=clock[0] + 2.0)
    assert orch.evaluate(r2).should_wake is True


def test_or_logic_hotword_or_clap():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    # Only hotword detected
    d1 = orch.evaluate(WakeSourceResult(source="hotword", detected=False, confidence=0.1))
    assert d1.should_wake is False
    # Only clap detected
    d2 = orch.evaluate(WakeSourceResult(source="double_clap", detected=True, confidence=0.9))
    assert d2.should_wake is True


def test_unknown_source_rejected():
    orch = WakeOrchestrator({"clock": _clock_fake, "allow_sources": {"hotword", "double_clap"}, "debug": False})
    result = WakeSourceResult(source="clap_unknown", detected=True, confidence=0.9)
    decision = orch.evaluate(result)
    assert decision.should_wake is False
    assert decision.reason == "source_not_allowed"


def test_reset():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False})
    orch.mark_listening_started()
    orch.reset()
    assert orch.get_status()["listening"] is False
    result = WakeSourceResult(source="hotword", detected=True, confidence=0.85)
    decision = orch.evaluate(result)
    assert decision.should_wake is True


def test_get_status():
    orch = WakeOrchestrator({"clock": _clock_fake, "debug": False})
    status = orch.get_status()
    assert "cooldown_ms" in status
    assert "suppress_while_listening" in status
    assert "allow_sources" in status
    assert "listening" in status
    assert "last_wake_at" in status
