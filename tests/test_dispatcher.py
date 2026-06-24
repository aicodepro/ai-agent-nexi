import pytest
from core.dispatcher import normalize_command, is_dispatching, current_source


def test_normalize_command():
    assert normalize_command("  hello   world  ") == "hello world"
    assert normalize_command("hi") == "hi"
    assert normalize_command("   ") == ""


def test_normalize_command_keeps_inner_spaces():
    result = normalize_command("open   chrome   browser")
    assert result == "open chrome browser"


def test_is_dispatching_default():
    assert is_dispatching() is False


def test_current_source_default():
    assert current_source() == ""
