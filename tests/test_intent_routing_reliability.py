from types import SimpleNamespace
from unittest.mock import patch

import pytest


def test_v2_router_retries_once_with_bounded_timeout(monkeypatch):
    import engine.groq_intent_router_v2 as router

    calls = []

    class Provider:
        def is_available(self):
            return True

        def route_with_schema(self, messages, schema, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise TimeoutError("first call timed out")
            return SimpleNamespace(
                ok=True,
                decision={"route": "brain", "intent": "general_qa", "confidence": 0.9},
                provider="test",
                model="test",
            )

    monkeypatch.setattr("engine.providers.get_intent_provider", lambda *_a, **_k: Provider())
    monkeypatch.setenv("GROQ_INTENT_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("GROQ_INTENT_MAX_RETRIES", "1")
    monkeypatch.setenv("GROQ_INTENT_TIMEOUT_SECONDS", "999")
    router._last_llm_call = 0.0

    result = router._route_with_llm("explain recursion", {})

    assert result["route"] == "brain"
    assert len(calls) == 2
    assert all(0 < timeout <= 10 for timeout in calls)


def test_legacy_planner_retries_once_with_bounded_timeout(monkeypatch):
    import engine.groq_intent_planner as planner

    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": '{"route":"brain","intent":"general_qa","confidence":0.9,"slots":{}}'}}]
            }

    def post(*_args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise TimeoutError("first call timed out")
        return Response()

    monkeypatch.setattr(planner.requests, "post", post)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_INTENT_MAX_RETRIES", "1")
    monkeypatch.setenv("GROQ_INTENT_TIMEOUT_SECONDS", "999")

    result = planner.classify_intent("maybe answer this", source="typed")

    assert result["route"] == "brain"
    assert len(calls) == 2
    assert all(0 < timeout <= 10 for timeout in calls)


def test_legacy_planner_malformed_output_is_not_reported_as_asr_failure(monkeypatch):
    import engine.groq_intent_planner as planner

    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"choices": [{"message": {"content": "not json"}}]},
    )
    monkeypatch.setattr(planner.requests, "post", lambda *_a, **_k: response)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    result = planner.classify_intent("maybe answer this", source="typed")

    assert result["route"] == "clarify"
    assert "didn't catch" not in result["clarification_question"].lower()
    assert "routing" in result["clarification_question"].lower()


def test_command_dispatch_uses_the_v2_decision_without_rerouting(monkeypatch):
    import engine.command as command

    decision = {"route": "system", "intent": "greeting", "slots": {}}
    monkeypatch.setenv("NEXI_ROUTER_PRIMARY", "1")
    monkeypatch.setattr("engine.groq_intent_router_v2.route_intent_v2", lambda *_a, **_k: decision)

    with patch("engine.router.route") as master_route, patch.object(command, "_speak_greeting"), patch.object(command, "_store_conversation_turn"):
        assert command._handle_product_intelligence_v2("hello", "typed") is True

    master_route.assert_not_called()


@pytest.mark.parametrize(
    "route,intent,slots",
    [
        ("workflow", "nexi_workflow_status", {}),
        ("system", "get_system_state", {}),
        ("memory", "recall_memory", {"query": "project"}),
        ("feature_gap", "request_feature", {"capability": "watch downloads"}),
    ],
)
def test_registered_tool_categories_execute_once(monkeypatch, route, intent, slots):
    import engine.command as command

    decision = {"route": route, "intent": intent, "slots": slots}
    monkeypatch.setattr("engine.groq_intent_router_v2.route_intent_v2", lambda *_a, **_k: decision)
    result = {"success": True, "verified": True, "message": "done"}

    with patch("engine.tool_registry.execute_tool", return_value=result) as execute, patch.object(command, "speak"), patch.object(command, "_store_conversation_turn"):
        assert command._handle_product_intelligence_v2("request", "typed") is True

    execute.assert_called_once_with(
        "request_feature" if route == "feature_gap" else intent,
        slots,
        confirmed=False,
    )


def test_model_supplied_confirmation_is_not_forwarded_as_user_consent(monkeypatch):
    import engine.command as command

    decision = {
        "route": "tool",
        "intent": "eye_mouse_control",
        "slots": {"mode": "control", "confirmed": True},
    }
    monkeypatch.setattr("engine.groq_intent_router_v2.route_intent_v2", lambda *_a, **_k: decision)
    result = {"success": False, "verified": False, "requires_confirmation": True, "message": "confirm"}

    with patch("engine.tool_registry.execute_tool", return_value=result) as execute, patch.object(command, "speak"), patch.object(command, "_store_conversation_turn"):
        assert command._handle_product_intelligence_v2("control the mouse", "typed") is True

    execute.assert_called_once_with(
        "eye_mouse_control",
        decision["slots"],
        confirmed=False,
    )


def test_unhandled_v2_category_clarifies_without_legacy_fallthrough(monkeypatch):
    import engine.command as command

    decision = {"route": "training", "intent": "training_answer", "slots": {"answer": "continue"}}
    monkeypatch.setattr("engine.groq_intent_router_v2.route_intent_v2", lambda *_a, **_k: decision)

    with patch.object(command, "_handle_cognitive_command", return_value=False), patch.object(command, "speak") as speak, patch.object(command, "_store_conversation_turn"):
        assert command._handle_product_intelligence_v2("continue", "typed") is True

    speak.assert_called_once()


def test_v2_router_error_clarifies_without_legacy_fallthrough(monkeypatch):
    import engine.command as command

    monkeypatch.setattr("engine.groq_intent_router_v2.route_intent_v2", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("router failed")))

    with patch.object(command, "speak") as speak, patch.object(command, "_store_conversation_turn"):
        assert command._handle_product_intelligence_v2("do something", "typed") is True

    speak.assert_called_once()


def test_router_normalization_preserves_explicit_url_path_and_numbers():
    from engine.groq_intent_router_v2 import _deterministic_router

    url = "https://Example.com/CasePath?id=1042"
    result = _deterministic_router(f"open {url}")

    assert result["slots"]["url"] == url


def test_legacy_planner_preserves_email_case_and_numbers_in_search_slot():
    from engine.groq_intent_planner import _deterministic_classify

    query = "User.Name+Tag@Example.COM invoice 1042"
    result = _deterministic_classify(f"search {query}")

    assert result["slots"]["query"] == query


def test_command_and_transcript_normalization_preserve_file_paths():
    from engine.command_bus import normalize_command
    from engine.transcript_filter import clean_transcript

    command = r"open C:\Users\Mark\Report 1042.txt"
    assert normalize_command(f"  {command}  ") == command
    assert clean_transcript(f"  {command}  ") == command


def test_parameter_extractor_retries_once_with_bounded_timeout(monkeypatch):
    import engine.llm_parameter_extractor as extractor

    calls = []
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"choices": [{"message": {"content": '{"slots":{"app_name":"chrome"},"missing":[]}'}}]},
    )

    def post(*_args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise TimeoutError("first call timed out")
        return response

    monkeypatch.setattr(extractor.requests, "post", post)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_INTENT_MAX_RETRIES", "1")
    monkeypatch.setenv("GROQ_INTENT_TIMEOUT_SECONDS", "999")

    result = extractor.extract_parameters("open chrome", "open_app")

    assert result["slots"] == {"app_name": "chrome"}
    assert len(calls) == 2
    assert all(0 < timeout <= 10 for timeout in calls)


def test_llm_rate_limit_is_source_scoped(monkeypatch):
    import engine.groq_intent_router_v2 as router

    monkeypatch.setenv("GROQ_INTENT_COOLDOWN_SECONDS", "60")
    router._last_llm_call = {}

    assert router._llm_rate_limited("typed") is False
    assert router._llm_rate_limited("voice-session-1") is False
    assert router._llm_rate_limited("typed") is True
