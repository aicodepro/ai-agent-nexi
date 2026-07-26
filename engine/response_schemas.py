"""Typed schemas for the answer NEXI is waiting for.

A pending question used to accept whatever arrived next. That is how
"show me your diagnostics" was stored as a folder name and "Create a folder"
became a folder called "Create a folder": the follow-up layer knew a reply was
due but not what KIND of reply, so any utterance satisfied it.

Each schema answers three questions:
  - is this value even the right kind of thing?
  - what is the normalized value to store?
  - if not, what should NEXI say to ask again?

Validation is deliberately conservative. Rejecting a good answer costs one
re-ask; accepting a bad one silently creates a folder named after a command.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    value: Any = None
    error: str = ""

    @staticmethod
    def accept(value: Any) -> "ValidationResult":
        return ValidationResult(True, value, "")

    @staticmethod
    def reject(error: str) -> "ValidationResult":
        return ValidationResult(False, None, error)


@dataclass(frozen=True)
class ResponseSchema:
    name: str
    description: str
    validate: Callable[[str], ValidationResult]
    reprompt: str


# Phrases that are a NEW instruction, never an answer to a question. A pending
# question must not swallow the user's next command.
_COMMAND_STARTS = (
    "open ", "create ", "make ", "search ", "play ", "close ", "start ",
    "launch ", "show ", "tell ", "read ", "delete ", "remove ", "write ",
    "find ", "stop ", "cancel ", "what ", "who ", "why ", "when ", "where ",
    "how ", "give me ", "can you ", "could you ",
)

_YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "affirmative",
        "go ahead", "do it", "confirm", "correct", "right", "please do"}
_NO = {"no", "nope", "nah", "negative", "don't", "do not", "cancel",
       "stop", "never mind", "nevermind", "forget it"}

_INVALID_PATH_CHARS = set('<>:"/\\|?*')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".!?")


def _looks_like_a_command(value: str) -> bool:
    low = value.lower()
    return low.startswith(_COMMAND_STARTS)


# --- validators --------------------------------------------------------------

def _validate_confirmation(text: str) -> ValidationResult:
    low = _clean(text).lower()
    if low in _YES:
        return ValidationResult.accept(True)
    if low in _NO:
        return ValidationResult.accept(False)
    return ValidationResult.reject("not_yes_or_no")


def _validate_name_like(text: str) -> ValidationResult:
    """A folder/file name. Rejects commands and characters the OS forbids."""
    value = _clean(text)
    if not value:
        return ValidationResult.reject("empty")
    if _looks_like_a_command(value):
        return ValidationResult.reject("looks_like_a_command")
    if value in (".", ".."):
        return ValidationResult.reject("reserved")
    if any(c in _INVALID_PATH_CHARS for c in value):
        return ValidationResult.reject("invalid_characters")
    if value.split(".")[0].strip().lower() in _WINDOWS_RESERVED:
        return ValidationResult.reject("reserved_by_windows")
    if len(value) > 200:
        return ValidationResult.reject("too_long")
    return ValidationResult.accept(value)


def _validate_location(text: str) -> ValidationResult:
    value = _clean(text)
    if not value:
        return ValidationResult.reject("empty")
    if _looks_like_a_command(value):
        return ValidationResult.reject("looks_like_a_command")
    return ValidationResult.accept(value)


def _validate_email(text: str) -> ValidationResult:
    value = _clean(text).replace(" at ", "@").replace(" dot ", ".").replace(" ", "")
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", value):
        return ValidationResult.accept(value)
    return ValidationResult.reject("not_an_email")


def _validate_number(text: str) -> ValidationResult:
    value = _clean(text).replace(",", "")
    try:
        return ValidationResult.accept(float(value) if "." in value else int(value))
    except ValueError:
        return ValidationResult.reject("not_a_number")


def _validate_app(text: str) -> ValidationResult:
    value = _clean(text)
    if not value:
        return ValidationResult.reject("empty")
    # "open chrome" answering "which app?" is the app, not a command.
    for prefix in ("open ", "launch ", "start "):
        if value.lower().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    if not value:
        return ValidationResult.reject("empty")
    return ValidationResult.accept(value)


def _validate_free_text(text: str) -> ValidationResult:
    value = _clean(text)
    return ValidationResult.accept(value) if value else ValidationResult.reject("empty")


SCHEMAS: dict[str, ResponseSchema] = {
    "confirmation": ResponseSchema(
        "confirmation", "yes or no", _validate_confirmation,
        "Please answer yes or no."),
    "folder_name": ResponseSchema(
        "folder_name", "a folder name", _validate_name_like,
        "What should I call the folder?"),
    "file_name": ResponseSchema(
        "file_name", "a file name", _validate_name_like,
        "What should I call the file?"),
    "folder_location": ResponseSchema(
        "folder_location", "where to create it", _validate_location,
        "Where should I create it?"),
    "app_name": ResponseSchema(
        "app_name", "an application", _validate_app,
        "Which app should I open?"),
    "email": ResponseSchema(
        "email", "an email address", _validate_email,
        "What is the email address?"),
    "number": ResponseSchema(
        "number", "a number", _validate_number,
        "Please say a number."),
    "query": ResponseSchema(
        "query", "what to search for", _validate_free_text,
        "What should I search for?"),
    "topic": ResponseSchema(
        "topic", "a topic", _validate_free_text,
        "Which topic?"),
    "free_text": ResponseSchema(
        "free_text", "any text", _validate_free_text,
        "Sorry, could you say that again?"),
}


def get_schema(name: str) -> ResponseSchema | None:
    return SCHEMAS.get((name or "").strip())


def validate_answer(schema_name: str, text: str) -> ValidationResult:
    """Validate a reply against the expected schema.

    An unknown schema falls back to free text rather than blocking the turn -
    a missing schema entry must not make NEXI unusable, only unvalidated.
    """
    schema = get_schema(schema_name)
    if schema is None:
        return _validate_free_text(text)
    return schema.validate(text)


def reprompt_for(schema_name: str) -> str:
    schema = get_schema(schema_name)
    return schema.reprompt if schema else "Sorry, could you say that again?"
