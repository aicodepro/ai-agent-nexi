import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


@pytest.fixture(autouse=True)
def _fresh():
    import engine.session_summary_manager as ssm
    ssm.reset_summary()
    yield
    ssm.reset_summary()


def test_keeps_plans_and_decisions():
    from engine.session_summary_manager import merge_exchange, get_summary
    merge_exchange({"user": "the plan is to refactor the router next", "assistant": "decided to use deterministic routing first"})
    s = get_summary().lower()
    assert "plan" in s or "refactor" in s
    assert "decided" in s or "deterministic" in s


def test_drops_small_talk():
    from engine.session_summary_manager import merge_exchange, get_summary
    merge_exchange({"user": "hi", "assistant": "hello"})
    merge_exchange({"user": "thanks", "assistant": "sure"})
    assert get_summary().strip() == ""


def test_secret_not_in_summary():
    from engine.session_summary_manager import merge_exchange, get_summary
    merge_exchange({"user": "my password=hunter2 and the plan is to login", "assistant": "ok will fix the bug"})
    s = get_summary()
    assert "hunter2" not in s


def test_to_context_bounded():
    from engine.session_summary_manager import merge_exchange, to_context
    for i in range(50):
        merge_exchange({"user": f"the plan step {i} to fix the bug in module {i}", "assistant": f"decided approach {i}"})
    ctx = to_context(max_chars=500)
    assert len(ctx) <= 500


def test_dedupe_points():
    from engine.session_summary_manager import merge_exchange, get_summary_manager
    merge_exchange({"user": "the plan is to ship today", "assistant": "ok"})
    merge_exchange({"user": "the plan is to ship today", "assistant": "ok"})
    # Same salient user point should not appear twice.
    summary = get_summary_manager().get_summary()
    assert summary.lower().count("the plan is to ship today") == 1
