"""Provider rate-limit breaker and follow-up slot binding. Offline.

Both guard defects seen in a live voice session where the Groq key was
rate-limited:
  - every turn made 4-6 separate dead HTTP calls, each waiting for its own 429;
  - an unrelated reply containing "name it" bound the NEXT utterance to a
    folder-name slot, swallowing "show me your diagnostics".
"""
from __future__ import annotations

import pytest

from engine.providers import openai_compat as oc


@pytest.fixture(autouse=True)
def _clear_breaker():
    oc._BREAKER_UNTIL.clear()
    yield
    oc._BREAKER_UNTIL.clear()


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}


def _call(monkeypatch, calls, status=429, headers=None):
    def fake_post(*_a, **_k):
        calls.append(1)
        return _Resp(status, headers)

    monkeypatch.setattr(oc.requests, "post", fake_post)
    return oc.chat_completion(
        base_url="https://x/v1", api_key="k", model="m",
        messages=[{"role": "user", "content": "hi"}], provider_name="groq",
    )


def test_one_429_stops_the_rest_of_the_turn(monkeypatch):
    """The 2nd..Nth caller in the same turn must not re-probe a dead provider."""
    calls: list[int] = []
    first = _call(monkeypatch, calls)
    assert first.ok is False
    assert len(calls) == 1

    for _ in range(5):
        later = _call(monkeypatch, calls)
        assert later.ok is False
        assert later.error_code == "rate_limited"
    assert len(calls) == 1, "breaker should have skipped the follow-up HTTP calls"


def test_retry_after_header_sets_the_cooldown(monkeypatch):
    _call(monkeypatch, [], headers={"Retry-After": "45"})
    assert 44.0 < oc._breaker_open_for("groq") <= 45.0


def test_absurd_retry_after_is_clamped(monkeypatch):
    _call(monkeypatch, [], headers={"Retry-After": "999999"})
    assert oc._breaker_open_for("groq") <= 300.0


def test_garbage_retry_after_falls_back_to_default(monkeypatch):
    _call(monkeypatch, [], headers={"Retry-After": "soon"})
    assert oc._breaker_open_for("groq") > 0


def test_breaker_is_per_provider(monkeypatch):
    _call(monkeypatch, [])
    assert oc._breaker_open_for("groq") > 0
    assert oc._breaker_open_for("openrouter") == 0.0


def test_non_429_does_not_trip_the_breaker(monkeypatch):
    _call(monkeypatch, [], status=500)
    assert oc._breaker_open_for("groq") == 0.0


# --- follow-up slot binding -------------------------------------------------

def test_unrelated_prose_does_not_bind_a_folder_slot():
    """Regression: "...want to name it?" made the next command a folder name."""
    from engine.assistant_response import infer_followup_type

    assert infer_followup_type("Saved to your workspace. Want to name it?") != "folder_name"
    assert infer_followup_type("I can rename it if you like.") != "folder_name"


def test_real_folder_prompt_still_binds():
    from engine.assistant_response import infer_followup_type

    assert infer_followup_type("What should I name the folder?") == "folder_name"
