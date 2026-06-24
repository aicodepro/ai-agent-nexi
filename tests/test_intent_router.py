import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.intent_router import route_intent, IntentResult


# ---------------------------------------------------------------------------
# General Q&A -> Lightning
# ---------------------------------------------------------------------------

def test_math_question_routes_to_lightning():
    r = route_intent("what is 2+2")
    assert r.route == "brain"
    assert r.intent == "general_qa"


def test_plain_math_routes_to_lightning():
    for q in ("2+2", "2 + 2", "10 * 5", "100 / 4", "(2+3)*4"):
        r = route_intent(q)
        assert r.route == "brain", f"{q!r} should be brain, got {r}"


def test_how_to_question_routes_to_lightning():
    r = route_intent("how to make pizza")
    assert r.route == "brain"


def test_explain_question_routes_to_lightning():
    r = route_intent("explain solar system")
    assert r.route == "brain"


def test_describe_question_routes_to_lightning():
    r = route_intent("describe the eiffel tower")
    assert r.route == "brain"


def test_who_is_celebrity_routes_to_lightning():
    r = route_intent("who is Elon Musk")
    assert r.route == "brain"


def test_why_question_routes_to_lightning():
    r = route_intent("why is the sky blue")
    assert r.route == "brain"


def test_write_request_routes_to_lightning():
    r = route_intent("write a short email")
    assert r.route == "brain"


def test_summarize_routes_to_lightning():
    r = route_intent("summarize this article")
    assert r.route == "brain"


# ---------------------------------------------------------------------------
# Greeting / Identity (exact only)
# ---------------------------------------------------------------------------

def test_hello_routes_to_greeting():
    for q in ("hello", "hi", "hey", "hola"):
        r = route_intent(q)
        assert r.route == "greeting", f"{q!r} should be greeting, got {r}"


def test_good_morning_routes_to_greeting():
    r = route_intent("good morning")
    assert r.route == "greeting"


def test_who_are_you_routes_to_identity():
    for q in ("who are you", "introduce yourself", "what is your name"):
        r = route_intent(q)
        assert r.route == "identity", f"{q!r} should be identity, got {r}"


def test_what_is_2_plus_2_does_not_route_to_identity_or_greeting():
    r = route_intent("what is 2+2")
    assert r.route != "identity"
    assert r.route != "greeting"
    assert r.route == "brain"


def test_hello_containing_question_does_not_match_greeting():
    # "hello, what is 2+2" must NOT route to greeting
    r = route_intent("hello, what is 2+2")
    assert r.route != "greeting"


# ---------------------------------------------------------------------------
# Local actions (hard local prefixes / exact)
# ---------------------------------------------------------------------------

def test_open_chrome_routes_to_local_action():
    r = route_intent("open chrome")
    assert r.route == "local_action"


def test_open_notepad_routes_to_local_action():
    r = route_intent("open notepad")
    assert r.route == "local_action"


def test_create_folder_routes_to_local_action():
    r = route_intent("create folder")
    assert r.route == "local_action"


def test_create_folder_with_args_routes_to_local_action():
    r = route_intent("create folder Test Folder on Desktop")
    assert r.route == "local_action"


def test_launch_chrome_routes_to_local_action():
    r = route_intent("launch chrome")
    assert r.route == "local_action"


def test_volume_up_routes_to_local_action():
    r = route_intent("volume up")
    assert r.route == "local_action"


def test_play_music_routes_to_local_action():
    r = route_intent("play music")
    assert r.route == "local_action"


def test_close_chrome_routes_to_local_action():
    r = route_intent("close chrome")
    assert r.route == "local_action"


# ---------------------------------------------------------------------------
# Q&A patterns that map to existing LOCAL intents
# ---------------------------------------------------------------------------

def test_what_is_the_time_stays_local():
    r = route_intent("what is the time")
    assert r.route == "local_action"


def test_what_is_the_weather_stays_local():
    r = route_intent("what is the weather")
    assert r.route == "local_action"


# ---------------------------------------------------------------------------
# Workflow priority
# ---------------------------------------------------------------------------

def test_workflow_active_routes_to_workflow_first():
    # When workflow is active, even plain replies go to workflow
    r = route_intent("Desktop", workflow_active=True)
    assert r.route == "workflow"
    assert r.intent == "reply"


def test_workflow_active_folder_name_routes_to_workflow():
    r = route_intent("Batch Three Test Folder", workflow_active=True)
    assert r.route == "workflow"


def test_workflow_active_yes_routes_to_workflow():
    r = route_intent("yes", workflow_active=True)
    assert r.route == "workflow"


def test_cancel_routes_to_workflow_when_active():
    r = route_intent("cancel", workflow_active=True)
    assert r.route == "workflow"
    assert r.intent == "cancel"


def test_stop_routes_to_workflow_when_active():
    r = route_intent("stop", workflow_active=True)
    assert r.route == "workflow"
    assert r.intent == "cancel"


def test_never_mind_routes_to_workflow_when_active():
    r = route_intent("never mind", workflow_active=True)
    assert r.route == "workflow"
    assert r.intent == "cancel"


def test_cancel_without_workflow_does_not_go_to_lightning_if_existing_stop_handler_exists():
    # Without workflow active, "cancel" / "stop" must stay local — they map
    # to existing stop_speaking / emergency_stop handlers, NOT to the brain chain.
    for q in ("cancel", "stop"):
        r = route_intent(q, workflow_active=False)
        assert r.route != "brain", f"{q!r} must not go to brain, got {r}"


# ---------------------------------------------------------------------------
# Default / unknown
# ---------------------------------------------------------------------------

def test_empty_query_is_unknown():
    r = route_intent("")
    assert r.route == "unknown"


def test_random_text_is_unknown_or_lightning_but_not_greeting():
    r = route_intent("xyzzy plover")
    assert r.route in ("unknown", "brain")
    assert r.route != "greeting"
    assert r.route != "identity"


# ---------------------------------------------------------------------------
# IntentResult shape
# ---------------------------------------------------------------------------

def test_intent_result_is_dataclass_like():
    r = route_intent("hello")
    assert isinstance(r, IntentResult)
    assert hasattr(r, "route")
    assert hasattr(r, "intent")
    assert hasattr(r, "confidence")
    assert hasattr(r, "reason")
    assert 0.0 <= r.confidence <= 1.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


