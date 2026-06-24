import intent.router as router
from intent.router import route_intent


def test_llm_rate_limited_throttles():
    router._last_llm_call = 0.0
    assert router._llm_rate_limited() is False   # first call passes
    assert router._llm_rate_limited() is True     # immediate second call throttled


def test_v2_disabled_short_circuits(monkeypatch):
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    result = router._route_with_groq("something ambiguous")
    assert result["route"] == "unknown"


def test_deterministic_path_unaffected():
    # The LLM hardening must not change the fast deterministic routing.
    assert route_intent("open chrome")["route"] == "local_action"
    assert route_intent("agent status")["route"] == "nexi"
    assert route_intent("what time is it")["intent"] == "get_time"


def test_cooldown_env_is_respected(monkeypatch):
    monkeypatch.setenv("GROQ_INTENT_COOLDOWN_SECONDS", "0")
    router._last_llm_call = 0.0
    assert router._llm_rate_limited() is False
    assert router._llm_rate_limited() is False  # zero cooldown never throttles
