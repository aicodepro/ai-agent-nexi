import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _mock_response(status=200, *, content=None, tool_calls=None):
    message = {}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"choices": [{"message": message}]}
    return resp


def test_provider_selection_by_env(monkeypatch):
    from engine.providers import get_intent_provider

    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "xai_grok")
    assert get_intent_provider().name == "xai_grok"
    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "groq")
    assert get_intent_provider().name == "groq"
    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "deterministic")
    assert get_intent_provider() is None


def test_xai_provider_unavailable_without_key(monkeypatch):
    from engine.providers.xai_grok_provider import XaiGrokProvider

    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert XaiGrokProvider().is_available() is False


def test_xai_structured_output_parses_decision(monkeypatch):
    from engine.providers.xai_grok_provider import XaiGrokProvider
    from engine.intent_taxonomy import router_decision_schema

    monkeypatch.setenv("XAI_API_KEY", "test-key")
    decision_json = (
        '{"route":"tool","intent":"open_app","domain":"desktop","confidence":0.95,'
        '"slots":{"app_name":"chrome"},"missing_slots":[],"risk_level":"none",'
        '"requires_confirmation":false,"reason":"open app"}'
    )
    with patch("engine.providers.openai_compat.requests.post", return_value=_mock_response(content=decision_json)) as post:
        result = XaiGrokProvider().route_with_schema(
            [{"role": "user", "content": "open chrome"}], router_decision_schema()
        )

    assert post.called
    # Verify the request targeted xAI and used json_schema response_format.
    _, kwargs = post.call_args
    assert "api.x.ai" in post.call_args[0][0]
    assert kwargs["json"]["response_format"]["type"] == "json_schema"
    assert result.ok is True
    assert result.decision["intent"] == "open_app"
    assert result.decision["slots"]["app_name"] == "chrome"
    assert result.provider == "xai_grok"


def test_xai_tool_call_path(monkeypatch):
    from engine.providers.xai_grok_provider import XaiGrokProvider
    from engine.tool_registry import xai_tools_schema

    monkeypatch.setenv("XAI_API_KEY", "test-key")
    tool_calls = [{"function": {"name": "open_app", "arguments": '{"app_name":"notepad"}'}}]
    with patch("engine.providers.openai_compat.requests.post", return_value=_mock_response(tool_calls=tool_calls)):
        result = XaiGrokProvider().route_with_tools(
            [{"role": "user", "content": "open notepad"}], xai_tools_schema()
        )

    assert result.ok is True
    assert result.tool_call["name"] == "open_app"
    assert result.tool_call["arguments"]["app_name"] == "notepad"


def test_xai_http_error_normalized(monkeypatch):
    from engine.providers.xai_grok_provider import XaiGrokProvider
    from engine.intent_taxonomy import router_decision_schema

    monkeypatch.setenv("XAI_API_KEY", "test-key")
    with patch("engine.providers.openai_compat.requests.post", return_value=_mock_response(status=500)):
        result = XaiGrokProvider().route_with_schema(
            [{"role": "user", "content": "x"}], router_decision_schema()
        )
    assert result.ok is False
    assert result.error_code == "http_500"


def test_router_uses_xai_when_configured(monkeypatch):
    """End-to-end: ambiguous text -> provider abstraction -> xAI structured output."""
    import engine.groq_intent_router_v2 as router

    monkeypatch.setenv("INTENT_ROUTER_PROVIDER", "xai_grok")
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "true")
    monkeypatch.setenv("GROQ_INTENT_COOLDOWN_SECONDS", "0")
    import engine.correction_learner as learner

    monkeypatch.setattr(learner, "apply_correction", lambda _t: {"matched": False})

    decision_json = (
        '{"route":"tool","intent":"open_app","domain":"desktop","confidence":0.93,'
        '"slots":{"app_name":"spotify"},"missing_slots":[],"risk_level":"none",'
        '"requires_confirmation":false,"reason":"fuzzy open"}'
    )
    ctx = {
        "source": "test", "pending_clarification": {}, "pending_followup": {},
        "active_workflow": {}, "active_training": {}, "latest_output": {"available": False},
        "recent_turns": [],
    }
    with patch("engine.providers.openai_compat.requests.post", return_value=_mock_response(content=decision_json)) as post:
        result = router.route_intent_v2("fire up spotify please", source="typed", context=ctx)

    assert post.called
    assert "api.x.ai" in post.call_args[0][0]
    assert result["route"] == "tool"
    assert result["intent"] == "open_app"
