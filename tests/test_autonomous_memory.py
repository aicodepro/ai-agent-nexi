import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("JARVIS_LAST_EXCHANGE_LIMIT", "10")
    import importlib
    import engine.session_summary_manager as ssm
    import engine.autonomous_memory as am
    importlib.reload(ssm)
    importlib.reload(am)
    am.get_autonomous_memory().clear_short_term()
    ssm.reset_summary()
    yield


def _exchange(mem, u, a):
    mem.add_user_message(u, source="test")
    mem.add_assistant_message(a, source="brain")


def test_keeps_only_last_10_raw_exchanges():
    from engine.autonomous_memory import get_autonomous_memory
    mem = get_autonomous_memory()
    for i in range(11):
        _exchange(mem, f"user message number {i} about the plan", f"assistant reply {i}")
    assert mem.exchange_count() == 10
    last = mem.get_last_exchanges()
    assert last[0]["user"].startswith("user message number 1")  # 0 overflowed
    assert last[-1]["user"].startswith("user message number 10")


def test_overflow_merged_into_rolling_summary():
    from engine.autonomous_memory import get_autonomous_memory, get_rolling_summary
    mem = get_autonomous_memory()
    for i in range(12):
        _exchange(mem, f"I need to fix the login bug step {i}", f"Plan: I will fix it in step {i}")
    summary = get_rolling_summary()
    assert summary  # overflow produced summary points
    assert "fix" in summary.lower() or "plan" in summary.lower()


def test_secret_text_blocked_from_exchanges():
    from engine.autonomous_memory import get_autonomous_memory
    mem = get_autonomous_memory()
    mem.add_user_message("my api_key=sk-supersecretvalue12345", source="test")
    mem.add_assistant_message("ok", source="brain")
    last = mem.get_last_exchanges()
    blob = " ".join(x["user"] + x["assistant"] for x in last)
    assert "supersecret" not in blob
    assert "sk-supersecret" not in blob


def test_build_context_includes_summary_and_recent_and_is_bounded(monkeypatch):
    from engine.autonomous_memory import get_autonomous_memory
    mem = get_autonomous_memory()
    for i in range(15):
        _exchange(mem, f"please remember the project deadline is friday {i}", f"noted deadline friday {i}")
    ctx = mem.build_context("deadline", max_chars=2000)
    assert len(ctx) <= 2000
    assert "Recent exchanges:" in ctx


def test_incomplete_user_then_assistant_pairs_correctly():
    from engine.autonomous_memory import get_autonomous_memory
    mem = get_autonomous_memory()
    mem.add_user_message("what is the plan for today", source="test")
    mem.add_assistant_message("the plan is to ship the router", source="brain")
    last = mem.get_last_exchanges()
    assert last[-1]["user"].startswith("what is the plan")
    assert last[-1]["assistant"].startswith("the plan is to ship")
