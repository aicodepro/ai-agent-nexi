import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_wake_candidate_emits_once_then_cooldown_blocks_duplicate():
    from engine.wake_arbitration_manager import WakeArbitrationManager, WakeCandidate

    clock = FakeClock()
    arb = WakeArbitrationManager({"clock": clock, "cooldown_ms": 1800, "debug": False})

    first = arb.evaluate(WakeCandidate("hotword", True, 0.8, clock(), "threshold"))
    assert first.should_wake is True
    assert first.source == "hotword"

    second = arb.evaluate(WakeCandidate("hotword", True, 0.9, clock(), "threshold"))
    assert second.should_wake is False
    assert second.cooldown_active is True
    assert second.reason == "cooldown"

    clock.advance(2.0)
    third = arb.evaluate(WakeCandidate("hotword", True, 0.9, clock(), "threshold"))
    assert third.should_wake is True


def test_suppresses_while_listening():
    from engine.wake_arbitration_manager import WakeArbitrationManager, WakeCandidate

    clock = FakeClock()
    arb = WakeArbitrationManager({"clock": clock, "cooldown_ms": 0})
    arb.mark_listening_started()

    decision = arb.evaluate(WakeCandidate("double_clap", True, 1.0, clock(), "double"))
    assert decision.should_wake is False
    assert decision.reason == "already_listening"

    arb.mark_listening_done()
    decision = arb.evaluate(WakeCandidate("double_clap", True, 1.0, clock(), "double"))
    assert decision.should_wake is True
    assert decision.source == "double_clap"


def test_clap_alias_normalises_to_double_clap():
    from engine.wake_arbitration_manager import WakeArbitrationManager, WakeCandidate

    clock = FakeClock()
    arb = WakeArbitrationManager({"clock": clock, "cooldown_ms": 0})
    decision = arb.evaluate(WakeCandidate("clap", True, 1.0, clock(), "double"))
    assert decision.should_wake is True
    assert decision.source == "double_clap"
