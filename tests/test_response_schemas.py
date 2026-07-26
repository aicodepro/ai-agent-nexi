"""A pending question must accept only the KIND of answer it asked for.

Without typed schemas the follow-up layer knew a reply was due but not what sort
of reply, so any utterance satisfied it:
  - "show me your diagnostics" was stored as a folder name;
  - "Create a folder" became a folder called "Create a folder".
"""
from __future__ import annotations

import pytest

from engine.response_schemas import validate_answer, reprompt_for, get_schema


# --- the live failures -------------------------------------------------------

@pytest.mark.parametrize("said", [
    "show me your diagnostics", "Create a folder", "open chrome",
    "what time is it", "play some music", "search for python",
])
def test_a_command_is_never_a_folder_name(said):
    assert validate_answer("folder_name", said).ok is False, f"{said!r} accepted as a name"


@pytest.mark.parametrize("name", [
    "Project Alpha", "Invoices 2026", "nexi-notes", "budget v2", "Q3 Report",
])
def test_real_names_are_accepted(name):
    result = validate_answer("folder_name", name)
    assert result.ok is True, f"{name!r} rejected"
    assert result.value == name


def test_os_invalid_characters_are_rejected():
    for bad in ['a/b', 'a:b', 'a?b', 'a*b', 'a|b', 'a"b']:
        assert validate_answer("folder_name", bad).ok is False, f"{bad!r} accepted"


def test_windows_reserved_names_are_rejected():
    for bad in ["con", "PRN", "aux", "nul", "com1", "lpt3"]:
        assert validate_answer("folder_name", bad).ok is False, f"{bad!r} accepted"


# --- confirmation ------------------------------------------------------------

@pytest.mark.parametrize("said,expected", [
    ("yes", True), ("yeah", True), ("sure", True), ("go ahead", True),
    ("no", False), ("nope", False), ("never mind", False),
])
def test_confirmation_parses_both_ways(said, expected):
    result = validate_answer("confirmation", said)
    assert result.ok is True
    assert result.value is expected


def test_confirmation_rejects_a_non_answer():
    """"Project Alpha" is not a yes/no and must not be read as consent."""
    assert validate_answer("confirmation", "Project Alpha").ok is False


# --- other typed slots -------------------------------------------------------

def test_email_accepts_spoken_form():
    result = validate_answer("email", "darsh at example dot com")
    assert result.ok is True
    assert result.value == "darsh@example.com"


def test_email_rejects_a_name():
    assert validate_answer("email", "Project Alpha").ok is False


def test_number_parses_and_rejects():
    assert validate_answer("number", "42").value == 42
    assert validate_answer("number", "3.5").value == 3.5
    assert validate_answer("number", "quite a lot").ok is False


def test_app_name_strips_the_verb():
    """"open chrome" answering "which app?" is the app, not a command."""
    result = validate_answer("app_name", "open chrome")
    assert result.ok is True
    assert result.value == "chrome"


def test_location_rejects_a_command_but_accepts_a_place():
    assert validate_answer("folder_location", "Desktop").ok is True
    assert validate_answer("folder_location", "open chrome").ok is False


# --- safety of the fallback --------------------------------------------------

def test_an_unknown_schema_does_not_block_the_turn():
    """A missing schema entry must leave NEXI usable, only unvalidated."""
    assert validate_answer("some_future_slot", "anything at all").ok is True


def test_empty_is_always_rejected():
    for schema in ("folder_name", "folder_location", "query", "free_text"):
        assert validate_answer(schema, "   ").ok is False


def test_every_schema_offers_a_reprompt():
    from engine.response_schemas import SCHEMAS
    for name in SCHEMAS:
        assert reprompt_for(name).strip().endswith(("?", ".")), name
        assert get_schema(name) is not None
