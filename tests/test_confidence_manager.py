import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_confidence_never_silent_idle():
    from engine.confidence_manager import build_clarification_question, should_clarify
    assert should_clarify(0.2, "clarify") is True
    assert build_clarification_question("zz")


def test_low_confidence_asks_clarification():
    from engine.confidence_manager import should_clarify
    assert should_clarify(0.64, "tool") is True
    assert should_clarify(0.90, "tool") is False
