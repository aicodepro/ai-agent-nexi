"""Rolling session summary — the compacted context NEXI carries between turns.

These tests were written against an API that does not exist (`to_context`,
`get_summary_manager`) and treated `get_summary()` as a string when it returns a dict of
category -> entries. Four of the five failed on ImportError/AttributeError.

The fifth, `test_secret_not_in_summary`, PASSED — and that was the dangerous one. It did
`assert "hunter2" not in get_summary()`, and `in` on a dict tests KEYS, so it could never
fail no matter what leaked. A redaction test that cannot fail is worse than no test: it
reports the guarantee is covered while covering nothing. It is asserted against the
rendered context string here.

Running these exposed the real bug: `merge_exchange` computed a summary entry and its
category and then never appended them, so the summary was permanently empty and the
ROLLING_SUMMARY section of the context budget always came back blank.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import engine.session_summary_manager as ssm


@pytest.fixture(autouse=True)
def _fresh():
    ssm.reset_summary()
    yield
    ssm.reset_summary()


def _all_entries() -> list[str]:
    return [entry for entries in ssm.get_summary().values() for entry in entries]


def test_records_a_salient_exchange():
    """REGRESSION: merge_exchange used to discard the entry it built."""
    ssm.merge_exchange({
        "user": "the plan is to refactor the router next",
        "assistant": "decided to use deterministic routing first",
    })
    assert _all_entries(), "a salient exchange must reach the summary"


def test_accepts_both_exchange_key_spellings():
    """autonomous_memory serialises exchanges with both spellings."""
    ssm.merge_exchange({"user_text": "the plan is to ship the router", "assistant_text": "ok"})
    from_long = len(_all_entries())
    ssm.reset_summary()
    ssm.merge_exchange({"user": "the plan is to ship the router", "assistant": "ok"})
    assert from_long == len(_all_entries()) == 1


def test_keeps_plans_and_decisions():
    ssm.merge_exchange({
        "user": "the plan is to refactor the router next",
        "assistant": "decided to use deterministic routing first",
    })
    context = ssm.build_summary_context().lower()
    assert "plan" in context or "refactor" in context
    assert "decided" in context or "deterministic" in context


def test_drops_small_talk():
    ssm.merge_exchange({"user": "hi", "assistant": "hello"})
    ssm.merge_exchange({"user": "thanks", "assistant": "sure"})
    assert _all_entries() == []


def test_secret_not_in_summary():
    """Asserted against the rendered string, not the dict — see module docstring."""
    ssm.merge_exchange({
        "user": "my password=hunter2 and the plan is to login",
        "assistant": "ok will fix the bug",
    })
    context = ssm.build_summary_context()
    assert context, "the exchange must be recorded, or this proves nothing"
    assert "hunter2" not in context
    assert "hunter2" not in str(ssm.get_summary())


def test_context_is_bounded():
    for i in range(50):
        ssm.merge_exchange({
            "user": f"the plan step {i} to fix the bug in module {i}",
            "assistant": f"decided approach {i}",
        })
    assert len(ssm.build_summary_context(max_chars=500)) <= 500


def test_summary_stays_under_max_length():
    """Unbounded growth would defeat the point — this exists to SAVE context."""
    for i in range(400):
        ssm.merge_exchange({
            "user": f"the plan step {i} is to fix the bug in module {i}",
            "assistant": f"decided approach {i} will be used later",
        })
    total = sum(len(e) for e in _all_entries())
    assert total <= ssm.MAX_SUMMARY_LENGTH


def test_dedupe_points():
    ssm.merge_exchange({"user": "the plan is to ship today", "assistant": "ok"})
    ssm.merge_exchange({"user": "the plan is to ship today", "assistant": "ok"})
    assert len(_all_entries()) == 1


def test_empty_exchange_is_ignored():
    ssm.merge_exchange({})
    ssm.merge_exchange({"user": "", "assistant": ""})
    ssm.merge_exchange({"user": "   ", "assistant": None})
    assert _all_entries() == []


def test_reset_clears_everything():
    ssm.merge_exchange({"user": "the plan is to ship today", "assistant": "ok"})
    assert _all_entries()
    ssm.reset_summary()
    assert _all_entries() == []
