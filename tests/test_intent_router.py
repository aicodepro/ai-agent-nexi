import pytest
from intent.router import route_intent, _norm


def test_route_math():
    result = route_intent("2 + 2")
    assert result["route"] == "brain"
    assert result["intent"] == "math"
    assert result["confidence"] >= 0.9


def test_route_math_complex():
    result = route_intent("15 * 3 + 2 / 7")
    assert result["route"] == "brain"
    assert result["intent"] == "math"


def test_route_greeting():
    result = route_intent("hello")
    assert result["route"] == "greeting"
    assert result["intent"] == "greeting"
    assert result["confidence"] == 1.0


def test_route_greeting_hi():
    result = route_intent("hi")
    assert result["route"] == "greeting"


def test_route_greeting_good_morning():
    result = route_intent("good morning")
    assert result["route"] == "greeting"


def test_route_time():
    result = route_intent("what time is it")
    assert result["route"] == "local_action"
    assert result["intent"] == "get_time"
    assert result["confidence"] == 1.0


def test_route_weather():
    result = route_intent("weather")
    assert result["route"] == "local_action"
    assert result["intent"] == "get_weather"


def test_route_open_app():
    result = route_intent("open chrome")
    assert result["route"] == "local_action"
    assert result["intent"] == "open_app"
    assert result["entity"] == "chrome"


def test_route_open_website():
    result = route_intent("go to youtube")
    assert result["route"] == "local_action"
    assert result["intent"] == "open_website"


def test_route_sleep():
    result = route_intent("go to sleep")
    assert result["route"] == "sleep"
    assert result["intent"] == "sleep"


def test_route_sleep_bye():
    result = route_intent("bye")
    assert result["route"] == "sleep"


def test_route_wake():
    result = route_intent("wake up")
    assert result["route"] == "system"
    assert result["intent"] == "wake"


def test_route_identity():
    result = route_intent("who are you")
    assert result["route"] == "identity"
    assert result["intent"] == "identity"


def test_route_empty():
    result = route_intent("")
    assert result["route"] == "unknown"
    assert result["intent"] == "unknown"


def test_route_whitespace():
    result = route_intent("   ")
    assert result["route"] == "unknown"


def test_route_cancel():
    result = route_intent("cancel")
    assert result["route"] == "cancel"


def test_route_repeat():
    result = route_intent("repeat that")
    assert result["route"] == "system"
    assert result["intent"] == "repeat"


def test_route_volume_up():
    result = route_intent("volume up")
    assert result["route"] == "local_action"
    assert result["intent"] == "volume_up"


def test_route_search():
    result = route_intent("search python tutorials")
    assert result["route"] == "local_action"
    assert result["intent"] == "web_search"
    assert "python tutorials" in result["entity"]


def test_route_remember():
    result = route_intent("remember that I like pizza")
    assert result["route"] == "memory"
    assert result["intent"] == "remember"


def test_route_list_tools():
    result = route_intent("list tools")
    assert result["route"] == "tool"


def test_route_qa_prefix():
    result = route_intent("what is the capital of France")
    assert result["route"] == "brain"
    assert result["intent"] == "general_qa"


def test_route_clipboard():
    result = route_intent("read clipboard")
    assert result["route"] == "local_action"
    assert result["intent"] == "read_clipboard"


def test_norm_keeps_operators():
    n = _norm("2 + 2")
    assert n == "2  2"


def test_norm_strips_punctuation():
    n = _norm("hello, world!")
    assert n == "hello world"


def test_norm_removes_special_chars():
    n = _norm("what's the weather?")
    assert "'" not in n
    assert "?" not in n
