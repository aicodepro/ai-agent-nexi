import pytest
from memory.rules import _norm, learn_rule, match_rule, clear_rules, list_rules
from pathlib import Path


def setup_function():
    import memory.rules as mr
    mr._save([])


@pytest.fixture(autouse=True)
def clean_rules():
    yield
    clear_rules()


def test_norm_preserves_percent():
    n = _norm("100% done")
    assert "%" in n
    assert n == "100% done"


def test_norm_strips_special():
    n = _norm("hello, world!!!")
    assert n == "hello world"


def test_norm_lowercases():
    n = _norm("HELLO There")
    assert n == "hello there"


def test_learn_and_match():
    msg = learn_rule("when i say test time, open chrome")
    assert "Got it" in msg
    assert match_rule("test time") == "open chrome"


def test_learn_overwrites():
    learn_rule("when i say hello, do thing")
    learn_rule("when i say hello, do other")
    assert match_rule("hello") == "do other"


def test_match_no_match():
    assert match_rule("nonexistent_trigger_xyz") == ""


def test_clear_rules():
    learn_rule("when i say foo, bar")
    n = clear_rules()
    assert n >= 1
    assert match_rule("foo") == ""
    assert list_rules() == []


def test_list_rules():
    learn_rule("when i say one, action1")
    learn_rule("when i say two, action2")
    rules = list_rules()
    assert len(rules) >= 2


def test_learn_invalid_syntax():
    msg = learn_rule("hello there")
    assert "Say it like" in msg
