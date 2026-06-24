import pytest
from memory.context import (
    add_turn, add_user_turn, add_assistant_turn,
    get_recent_turns, get_last_assistant_response, clear, get_working_memory,
)


def setup_function():
    clear()


def test_add_and_get_turns():
    add_user_turn("hello")
    add_assistant_turn("hi there!")
    turns = get_recent_turns(10)
    assert len(turns) >= 2
    assert turns[-2]["role"] == "user"
    assert turns[-2]["text"] == "hello"
    assert turns[-1]["role"] == "assistant"
    assert turns[-1]["text"] == "hi there!"


def test_get_last_response():
    add_assistant_turn("this is a response")
    assert get_last_assistant_response() == "this is a response"


def test_get_last_response_empty():
    clear()
    assert get_last_assistant_response() == ""


def test_clear():
    add_user_turn("something")
    add_assistant_turn("reply")
    clear()
    assert get_last_assistant_response() == ""
    assert len(get_recent_turns(10)) == 0


def test_clean_truncates():
    long_text = "a" * 1000
    add_user_turn(long_text)
    turns = get_recent_turns(10)
    last = turns[-1]
    assert len(last["text"]) <= 500


def test_working_memory():
    clear()
    add_user_turn("hello")
    add_assistant_turn("hi!")
    wm = get_working_memory(limit=8, max_chars=2500)
    assert "User: hello" in wm
    assert "Nexi: hi!" in wm


def test_working_memory_empty():
    clear()
    assert get_working_memory() == ""


def test_add_turn_with_metadata():
    add_turn("user", "test", source="voice", intent="greeting", route="greeting",
             metadata={"confidence": 0.9})
    turns = get_recent_turns(1)
    assert turns[0]["source"] == "voice"
    assert turns[0]["intent"] == "greeting"
    assert turns[0]["route"] == "greeting"
    assert turns[0]["metadata"]["confidence"] == 0.9


def test_empty_text_ignored():
    clear()
    add_user_turn("")
    assert len(get_recent_turns(10)) == 0
