"""Tests for combined wake OR logic (Phase 6)."""

from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult


def _make_clock(start=1000.0, step=5.0):
    """Returns a clock that advances on each call, avoiding cooldown."""
    t = [start]
    def clock():
        val = t[0]
        t[0] += step
        return val
    return clock


def test_hotword_wakes():
    orch = WakeOrchestrator({"clock": _make_clock(), "debug": False})
    d = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=0.85))
    assert d.should_wake is True
    assert d.source == "hotword"


def test_double_clap_wakes():
    orch = WakeOrchestrator({"clock": _make_clock(), "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    d = orch.evaluate(WakeSourceResult(source="double_clap", detected=True, confidence=0.88))
    assert d.should_wake is True
    assert d.source == "double_clap"


def test_hotword_or_clap_wakes():
    """Each test pair uses its own orchestrator to avoid cooldown."""
    cases = [
        (WakeSourceResult(source="hotword", detected=True, confidence=0.85), True, "hotword"),
        (WakeSourceResult(source="hotword", detected=False, confidence=0.1), False, ""),
        (WakeSourceResult(source="double_clap", detected=True, confidence=0.9), True, "double_clap"),
        (WakeSourceResult(source="double_clap", detected=False, confidence=0.05), False, ""),
    ]
    for result, expect_wake, expect_source in cases:
        orch = WakeOrchestrator({"clock": _make_clock(), "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
        d = orch.evaluate(result)
        assert d.should_wake == expect_wake, \
            f"Expected wake={expect_wake} for source={result.source} detected={result.detected}"
        if expect_wake:
            assert d.source == expect_source, \
                f"Expected source={expect_source}, got {d.source}"


def test_both_detected_one_wake():
    """When both hotword and clap are detected, first one wins."""
    orch = WakeOrchestrator({"clock": _make_clock(), "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    d1 = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=0.85))
    assert d1.should_wake is True
    orch.mark_listening_started()
    d2 = orch.evaluate(WakeSourceResult(source="double_clap", detected=True, confidence=0.92))
    assert d2.should_wake is False
    assert d2.reason == "already_listening"


def test_no_duplicate_wakes_after_wake():
    """Only one wake event per detection cycle."""
    clock = [1000.0]
    def advancing():
        val = clock[0]
        clock[0] += 0.5
        return val
    orch = WakeOrchestrator({"clock": advancing, "cooldown_ms": 1800, "debug": False, "allow_sources": {"hotword", "double_clap", "hotkey"}})
    d1 = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=0.85))
    assert d1.should_wake is True
    d2 = orch.evaluate(WakeSourceResult(source="double_clap", detected=True, confidence=0.92))
    assert d2.should_wake is False
    assert d2.reason == "cooldown"
