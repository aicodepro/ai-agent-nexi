"""Bare API keys were stored in cleartext.

Both redactors only matched LABELLED secrets ("api_key: x", "token=y"). A key that
arrives without a label — pasted into chat, read aloud ("my key is gsk_..."),
echoed out of a config file, or captured by screen_read — matched nothing and was
written to the memory store verbatim, then re-surfaced by recall_memory.

Nexi's own .env holds live Groq and Gemini keys, so this is the realistic path.

All keys below are SYNTHETIC — same shape as the real formats, not real values.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import memory_safety
from engine.memory import memory_redaction

# Shape-accurate fakes: gsk_ + 52 alnum, AIza + 35, etc.
FAKE_KEYS = [
    "gsk_" + "aB3" * 17 + "z",                      # Groq
    "AIza" + "Sy" + "K7n2Qw" * 5 + "aBc",           # Google / Gemini
    "sk-ant-api03-" + "x9Y" * 12,                   # Anthropic
    "sk-proj-" + "Tk4" * 10,                        # OpenAI
    "ghp_" + "b7Q" * 12,                            # GitHub
    "xoxb-" + "1234567890-abcdefghij",              # Slack
    "AKIA" + "IOSFODNN7EXAMPLE",                    # AWS
    "hf_" + "QwErTy" * 6,                           # HuggingFace
]

REDACTORS = [
    pytest.param(memory_safety.redact_sensitive, id="memory_safety"),
    pytest.param(memory_redaction.redact_sensitive, id="memory_redaction"),
]


@pytest.mark.parametrize("redact", REDACTORS)
@pytest.mark.parametrize("key", FAKE_KEYS)
def test_a_bare_key_is_redacted(redact, key):
    out = redact(f"remember this for me: {key}")
    assert key not in out, f"{key[:8]}... survived redaction: {out!r}"
    assert "[REDACTED]" in out


@pytest.mark.parametrize("redact", REDACTORS)
def test_a_key_spoken_mid_sentence_is_redacted(redact):
    key = FAKE_KEYS[0]
    out = redact(f"my groq key is {key} please save it")
    assert key not in out
    # the surrounding words must survive — this is a redactor, not a deleter
    assert "groq" in out and "save it" in out


@pytest.mark.parametrize("key", FAKE_KEYS)
def test_a_bare_key_is_not_stored_at_all(key):
    ok, reason = memory_safety.is_safe_to_store(f"note to self: {key}")
    assert ok is False, f"{key[:8]}... would be written to the memory store"
    assert reason == "secret_or_sensitive"


@pytest.mark.parametrize("redact", REDACTORS)
def test_ordinary_text_is_left_alone(redact):
    """A redactor that eats normal speech is worse than no redactor — Nexi would
    forget real facts. These all contain key-ish prefixes but are not keys."""
    for benign in [
        "the sky is blue",
        "remind me to buy milk",
        "ask about the AI project status",
        "skip that task",
        "my name is Darsh",
    ]:
        assert redact(benign) == benign, f"clobbered benign text: {benign!r}"


def test_benign_text_is_still_storable():
    ok, _ = memory_safety.is_safe_to_store("remind me to buy milk")
    assert ok is True
