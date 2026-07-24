"""OpenRouter provider + model_registry endpoint routing (idea #112).

"NEXI must switch any model per task" needs one seam that reaches every vendor.
OpenRouter is an OpenAI-compatible gateway (Anthropic/OpenAI/Google/Meta + free
models), so the provider reuses openai_compat and model_registry.endpoint_for()
resolves each model id to the right base_url + key.

Live calls are blocked in the tool sandbox (image/large POSTs die at the proxy), so
these mock the transport and assert MY routing is correct: the request goes to
openrouter.ai with the OpenRouter key, defaults stay on Groq so nothing regresses,
and an unknown vendor id still routes to OpenRouter when its key is present.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import model_registry as reg


# ---- endpoint resolution -------------------------------------------------------

def test_known_groq_model_routes_to_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    ep = reg.endpoint_for("llama-3.3-70b-versatile")
    assert ep["provider"] == "groq"
    assert "api.groq.com" in ep["base_url"]


def test_known_openrouter_model_routes_to_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    ep = reg.endpoint_for("anthropic/claude-sonnet-4.5")
    assert ep["provider"] == "openrouter"
    assert "openrouter.ai" in ep["base_url"]
    assert ep["api_key"] == "or-key"


def test_unknown_vendor_id_routes_to_openrouter_when_key_present(monkeypatch):
    """A brand-new model set via env override must work without editing MODELS."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    ep = reg.endpoint_for("x-ai/grok-4-fast")
    assert ep["provider"] == "openrouter"


def test_unknown_id_without_openrouter_key_defaults_to_groq(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    ep = reg.endpoint_for("some/unknown-model")
    assert ep["provider"] == "groq"


# ---- select_model does not strand NEXI on an uncallable model ------------------

def test_autoselect_stays_on_groq_when_only_groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    for task in ("intent_json", "react_tools"):
        chosen = reg.select_model(task)
        assert reg.endpoint_for(chosen)["provider"] == "groq", (
            f"{task} picked {chosen}, which needs a key NEXI doesn't have"
        )


def test_env_override_can_force_an_openrouter_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("REACT_MODEL", "anthropic/claude-sonnet-4.5")
    assert reg.select_model("react_tools") == "anthropic/claude-sonnet-4.5"
    assert reg.endpoint_for(reg.select_model("react_tools"))["provider"] == "openrouter"


# ---- the provider actually dispatches to OpenRouter ----------------------------

def test_provider_calls_openrouter_endpoint(monkeypatch):
    from engine.providers import openrouter_provider as orp

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": '{"ok":1}'}}]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("engine.providers.openai_compat.requests.post", _fake_post)

    res = orp.OpenRouterProvider().route_with_schema(
        [{"role": "user", "content": "hi"}], schema={}, model="anthropic/claude-sonnet-4.5")

    assert res.ok
    assert "openrouter.ai/api/v1/chat/completions" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer or-secret"
    assert captured["json"]["model"] == "anthropic/claude-sonnet-4.5"


def test_provider_unavailable_without_key(monkeypatch):
    from engine.providers import openrouter_provider as orp
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert orp.OpenRouterProvider().is_available() is False


def test_optional_attribution_headers_do_not_break_auth(monkeypatch):
    from engine.providers import openrouter_provider as orp

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://nexi.local")
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": "{}"}}]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        return _Resp()

    monkeypatch.setattr("engine.providers.openai_compat.requests.post", _fake_post)
    orp.OpenRouterProvider().route_with_schema([{"role": "user", "content": "x"}], schema={})

    assert captured["headers"]["Authorization"] == "Bearer or-secret"  # not clobbered
    assert captured["headers"]["HTTP-Referer"] == "https://nexi.local"
