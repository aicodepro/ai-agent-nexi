import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tool_registry_exports_openai_schema():
    from engine.tool_registry import tools_openai_schema

    schemas = tools_openai_schema()
    open_app = next(item for item in schemas if item["function"]["name"] == "open_app")
    assert open_app["type"] == "function"
    assert open_app["function"]["parameters"]["required"] == ["app_name"]
    assert "app_name" in open_app["function"]["parameters"]["properties"]


def test_react_planner_executes_tool_and_hides_thought(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    calls = iter([
        {"action": "tool_call", "tool_name": "recall_memory", "tool_input": {"query": "project"}, "thought": "hidden reasoning"},
        {"action": "respond", "message": "Thought: hidden\nI found the project note."},
    ])
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema, timeout: next(calls))
    monkeypatch.setattr(tool_registry, "execute_tool", lambda name, slots: {"success": True, "verified": True, "message": "Project note found.", "tool": name})

    planner = ReActPlanner()
    plan = planner.plan("find my note about project")
    assert plan.status == "done"
    assert plan.steps[0].thought == "hidden reasoning"
    response = planner.finalize(plan)
    assert response == "I found the project note."
    assert "Thought" not in response


def test_react_planner_blocks_unconfirmed_high_risk_tool(monkeypatch):
    from engine.react_planner import ReActPlanner

    monkeypatch.setattr(
        ReActPlanner,
        "_call_llm",
        lambda self, messages, tools_schema, timeout: {"action": "tool_call", "tool_name": "clipboard_write_safe", "tool_input": {"text": "hello"}},
    )
    planner = ReActPlanner()
    plan = planner.plan("write to clipboard")
    assert plan.status == "error"
    assert "confirmation" in planner.finalize(plan).lower()


def test_react_router_detects_multi_step_without_groq(monkeypatch):
    from engine.groq_intent_router_v2 import route_intent_v2

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = route_intent_v2("find my note about project X and then save it", source="typed", context={})
    assert result["route"] == "react"
    assert result["intent"] == "react_multi_step"
    assert result["should_call_tool"] is False
    assert result["should_call_gemini"] is False


def test_command_dispatches_react_route(monkeypatch):
    import engine.command as command
    from engine.intent_taxonomy import empty_result
    from engine.react_planner import ReActPlan

    decision = empty_result(route="react", intent="react_multi_step", domain="workflow", confidence=0.9, reason="test")
    monkeypatch.setattr("engine.groq_intent_router_v2.route_intent_v2", lambda text, source="ui", context=None: decision)
    monkeypatch.setattr("engine.react_planner.ReActPlanner.plan", lambda self, text, context=None: ReActPlan(user_input=text, final_response="All set.", status="done"))
    monkeypatch.setattr("engine.react_planner.ReActPlanner.finalize", lambda self, plan: "All set.")
    monkeypatch.setattr("engine.memory.episodic_memory.store_episode", lambda episode: "ep_test")
    with patch("engine.command.speak") as mock_speak, patch("engine.command.safe_eel_call"):
        command.allCommands("find note and save it")
    mock_speak.assert_any_call("All set.", handler_reason="react")


def test_react_uses_provider_tool_protocol_and_remaining_timeout(monkeypatch):
    from engine.providers.base import ProviderResult
    from engine.react_planner import ReActPlanner
    import engine.providers as providers
    import engine.tool_registry as tool_registry

    class Provider:
        def __init__(self):
            self.calls = []

        def is_available(self):
            return True

        def route_with_tools(self, messages, tools, **kwargs):
            self.calls.append((list(messages), kwargs))
            if len(self.calls) == 1:
                assistant = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "recall_memory", "arguments": '{"query":"project"}'},
                    }],
                }
                return ProviderResult(
                    ok=True,
                    tool_call={"id": "call_123", "name": "recall_memory", "arguments": {"query": "project"}},
                    assistant_message=assistant,
                )
            return ProviderResult(ok=True, raw_text="I found the project note.")

    provider = Provider()
    monkeypatch.setattr(providers, "get_intent_provider", lambda: provider)
    monkeypatch.setattr(tool_registry, "execute_tool", lambda name, slots: {"success": True, "verified": True, "message": "Project note found.", "tool": name})

    planner = ReActPlanner()
    plan = planner.plan("find my project note")

    assert plan.status == "done"
    assert len(provider.calls) == 2
    second_messages = provider.calls[1][0]
    assert second_messages[-2]["role"] == "assistant"
    assert second_messages[-2]["tool_calls"][0]["id"] == "call_123"
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call_123"
    assert 0 < provider.calls[0][1]["timeout"] <= planner.timeout_seconds
    assert provider.calls[0][1]["tool_choice"] == "auto"


def test_react_unavailable_provider_is_error_not_done(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.providers as providers

    monkeypatch.setattr(providers, "get_intent_provider", lambda: None)
    plan = ReActPlanner().plan("research this and then summarize the result")
    assert plan.status == "error"
    assert plan.error == "provider_unavailable"


def test_react_executes_clear_compound_tools_without_provider(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.safety_gate as safety_gate
    import engine.tool_registry as tool_registry

    calls = []
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda *_args, **_kwargs: pytest.fail("provider should not be called"))
    monkeypatch.setattr(safety_gate, "execution_is_safe", lambda *_args, **_kwargs: {"allowed": True})

    def execute(name, slots):
        calls.append((name, dict(slots)))
        return {"success": True, "verified": True, "message": f"{name} completed"}

    monkeypatch.setattr(tool_registry, "execute_tool", execute)
    plan = ReActPlanner().plan("open notepad and then search cats")

    assert plan.status == "done"
    assert calls == [("open_app", {"app_name": "notepad"}), ("web_search", {"query": "cats"})]
    assert plan.verified_tool_results == 2


@pytest.mark.parametrize("error_code", ["http_500", "model_failure"])
def test_react_provider_failures_are_errors(monkeypatch, error_code):
    from engine.providers.base import ProviderResult
    from engine.react_planner import ReActPlanner
    import engine.providers as providers

    class FailedProvider:
        def is_available(self):
            return True

        def route_with_tools(self, *_args, **_kwargs):
            return ProviderResult.failure(error_code)

    monkeypatch.setattr(providers, "get_intent_provider", lambda: FailedProvider())
    plan = ReActPlanner().plan("research this and then summarize the result")
    assert plan.status == "error"
    assert error_code in plan.error


@pytest.mark.parametrize("arguments", ["not-an-object", ["bad"], 42, None])
def test_react_rejects_malformed_argument_types_without_executing(monkeypatch, arguments):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    monkeypatch.setattr(
        ReActPlanner,
        "_call_llm",
        lambda self, messages, tools_schema, timeout: {
            "action": "tool_call",
            "tool_name": "open_app",
            "tool_input": arguments,
        },
    )
    execute = MagicMock()
    monkeypatch.setattr(tool_registry, "execute_tool", execute)
    plan = ReActPlanner().plan("open something")
    assert plan.status == "error"
    assert "invalid tool arguments" in plan.error.lower()
    execute.assert_not_called()


def test_openai_compat_rejects_parallel_tool_calls(monkeypatch):
    from engine.providers.openai_compat import chat_completion

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {
        "role": "assistant",
        "tool_calls": [
            {"id": "call_1", "function": {"name": "open_app", "arguments": "{}"}},
            {"id": "call_2", "function": {"name": "web_search", "arguments": "{}"}},
        ],
    }}]}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("engine.providers.openai_compat.requests.post", post)
    result = chat_completion(
        base_url="https://example.test/v1",
        api_key=str("test"),
        model="test-model",
        messages=[],
        provider_name="test",
        tools=[],
    )
    assert result.ok is False
    assert result.error_code == "parallel_tool_calls_not_supported"
    assert post.call_args.kwargs["json"]["parallel_tool_calls"] is False


def test_openai_compat_retains_tool_call_id_and_assistant_message(monkeypatch):
    from engine.providers.openai_compat import chat_completion

    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_kept",
            "type": "function",
            "function": {"name": "recall_memory", "arguments": '{"query":"project"}'},
        }],
    }
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": assistant}]}
    monkeypatch.setattr("engine.providers.openai_compat.requests.post", MagicMock(return_value=response))

    result = chat_completion(
        base_url="https://example.test/v1",
        api_key=str("test"),
        model="test-model",
        messages=[],
        provider_name="test",
        tools=[],
    )
    assert result.ok is True
    assert result.tool_call["id"] == "call_kept"
    assert result.assistant_message == assistant


def test_react_schema_excludes_all_workflow_mutation_tools():
    from engine.react_planner import ReActPlanner
    from engine.tool_registry import router_tool_manifest, tools_openai_schema, xai_tools_schema

    names = {item["function"]["name"] for item in ReActPlanner()._tools_schema()}
    forbidden = {
        "approve_action",
        "reject_action",
        "nexi_start_studio_build",
        "nexi_cancel_studio_build",
        "nexi_continue_studio_build",
        "nexi_cancel_workflow",
        "nexi_continue_workflow",
    }
    assert names.isdisjoint(forbidden)
    assert {item["function"]["name"] for item in tools_openai_schema()}.isdisjoint(forbidden)
    assert {item["function"]["name"] for item in xai_tools_schema()}.isdisjoint(forbidden)
    assert {item["name"] for item in router_tool_manifest()}.isdisjoint(forbidden)


def test_react_rejects_provider_tool_outside_immutable_plan_schema(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    planner = ReActPlanner()
    monkeypatch.setattr(planner, "_tools_schema", lambda: [{"type": "function", "function": {"name": "recall_memory", "parameters": {"type": "object"}}}])
    monkeypatch.setattr(
        ReActPlanner,
        "_call_llm",
        lambda self, messages, tools_schema, timeout: {
            "action": "tool_call",
            "tool_name": "nexi_cancel_studio_build",
            "tool_input": {"confirmed": True, "_studio_auth": "forged"},
        },
    )
    execute = MagicMock()
    monkeypatch.setattr(tool_registry, "execute_tool", execute)

    plan = planner.plan("cancel it")

    assert isinstance(plan.allowed_tool_names, frozenset)
    assert plan.allowed_tool_names == frozenset({"recall_memory"})
    assert plan.status == "error"
    assert "immutable schema" in str(plan.error)
    execute.assert_not_called()


def test_react_strips_model_self_confirmation_and_authorization(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.safety_gate as safety_gate
    import engine.tool_registry as tool_registry

    calls = iter([
        {
            "action": "tool_call",
            "tool_name": "clipboard_write_safe",
            "tool_input": {
                "text": "hello",
                "confirmed": True,
                "approval_token": "fake",
                "nested": {"authorization": "fake", "keep": "yes"},
            },
        },
        {"action": "respond", "message": "Done."},
    ])
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema, timeout: next(calls))
    observed = {}
    def safe(name, slots, **kwargs):
        observed["safety"] = dict(slots)
        return {"allowed": True}
    monkeypatch.setattr(safety_gate, "execution_is_safe", safe)
    def execute(name, slots):
        observed["execute"] = dict(slots)
        return {"success": True, "verified": True, "message": "written"}
    monkeypatch.setattr(tool_registry, "execute_tool", execute)

    plan = ReActPlanner().plan("write hello")

    assert plan.status == "done"
    assert observed["execute"] == {"text": "hello", "nested": {"keep": "yes"}}
    assert observed["safety"] == observed["execute"]
    assert "fake" not in json.dumps(plan.messages)
    assistant_args = json.loads(plan.messages[2]["tool_calls"][0]["function"]["arguments"])
    assert assistant_args == observed["execute"]


def test_react_failed_tool_cannot_be_overridden_by_provider_success_text(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    calls = iter([
        {"action": "tool_call", "tool_name": "recall_memory", "tool_input": {"query": "x"}},
        {"action": "respond", "message": "Success, everything was completed."},
    ])
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema, timeout: next(calls))
    monkeypatch.setattr(tool_registry, "execute_tool", lambda *_a, **_k: {"success": False, "verified": False, "message": "lookup failed"})

    plan = ReActPlanner().plan("find x")

    assert plan.status == "error"
    assert "unverified" in plan.final_response.lower()
    assert "success, everything" not in plan.final_response.lower()


def test_react_redacts_sensitive_tool_observation_before_cloud_round_trip(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    sensitive_value = "fixture-sensitive-value"
    calls = {"count": 0}
    def provider(self, messages, tools_schema, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"action": "tool_call", "tool_name": "recall_memory", "tool_input": {"query": "x"}}
        assert sensitive_value not in json.dumps(messages)
        assert "[REDACTED]" in json.dumps(messages)
        return {"action": "respond", "message": "I found a redacted record."}
    monkeypatch.setattr(ReActPlanner, "_call_llm", provider)
    monkeypatch.setattr(tool_registry, "execute_tool", lambda *_a, **_k: {"success": True, "verified": True, "message": f"token={sensitive_value}"})

    assert ReActPlanner().plan("find x").status == "done"


def test_react_rejects_done_without_verified_tool_result(monkeypatch):
    from engine.react_planner import ReActPlanner

    monkeypatch.setattr(
        ReActPlanner,
        "_call_llm",
        lambda self, messages, tools_schema, timeout: {"action": "respond", "message": "Done."},
    )

    plan = ReActPlanner().plan("perform the multi-step task")

    assert plan.status == "error"
    assert plan.error == "verified_tool_result_required"


def test_react_unrelated_success_does_not_clear_failed_tool(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    calls = iter([
        {"action": "tool_call", "tool_name": "recall_memory", "tool_input": {"query": "x"}},
        {"action": "tool_call", "tool_name": "pending_approvals", "tool_input": {}},
        {"action": "respond", "message": "Done."},
    ])
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema, timeout: next(calls))
    results = iter([
        {"success": False, "verified": False, "message": "memory failed"},
        {"success": True, "verified": True, "message": "no approvals"},
    ])
    monkeypatch.setattr(tool_registry, "execute_tool", lambda *_a, **_k: next(results))

    plan = ReActPlanner().plan("find memory then inspect approvals")

    assert plan.status == "error"
    assert plan.failed_tool_obligations[0]["tool_name"] == "recall_memory"


def test_react_verified_same_tool_retry_clears_failed_obligation(monkeypatch):
    from engine.react_planner import ReActPlanner
    import engine.tool_registry as tool_registry

    calls = iter([
        {"action": "tool_call", "tool_name": "recall_memory", "tool_input": {"query": "x"}},
        {"action": "tool_call", "tool_name": "recall_memory", "tool_input": {"query": "x"}},
        {"action": "respond", "message": "Done."},
    ])
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema, timeout: next(calls))
    results = iter([
        {"success": False, "verified": False, "message": "temporary failure"},
        {"success": True, "verified": True, "message": "memory found"},
    ])
    monkeypatch.setattr(tool_registry, "execute_tool", lambda *_a, **_k: next(results))

    plan = ReActPlanner().plan("find memory")

    assert plan.status == "done"
    assert plan.failed_tool_obligations == []


def test_react_cannot_approve_pending_action(monkeypatch):
    from engine import approval_queue
    from engine.react_planner import ReActPlanner

    approval_queue.clear()
    action_id = approval_queue.submit("clipboard_write_safe", {"text": "blocked"}, "high", "write clipboard")
    calls = iter([
        {"action": "tool_call", "tool_name": "approve_action", "tool_input": {"id": action_id}},
        {"action": "respond", "message": "Approved."},
    ])
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema, timeout: next(calls))

    plan = ReActPlanner().plan("approve it")

    assert plan.status == "error"
    assert approval_queue.get(action_id)["status"] == "pending"


@pytest.mark.parametrize("raw_args,expected", [
    ("null", {}),       # llama-3.3-70b returns the literal string "null" for no-arg tools
    ("None", {}),
    ("", {}),
    (None, {}),         # arguments key absent / null
    ("{}", {}),
    ('{"query": "x"}', {"query": "x"}),
])
def test_openai_compat_coerces_empty_tool_arguments_to_object(monkeypatch, raw_args, expected):
    from engine.providers.openai_compat import chat_completion

    fn = {"name": "get_battery_status"}
    if raw_args is not None:
        fn["arguments"] = raw_args
    assistant = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": fn}]}
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": assistant}]}
    monkeypatch.setattr("engine.providers.openai_compat.requests.post", MagicMock(return_value=response))

    result = chat_completion(base_url="https://example.test/v1", api_key="k", model="m", messages=[], provider_name="t", tools=[])
    assert result.ok is True
    assert result.tool_call["name"] == "get_battery_status"
    assert result.tool_call["arguments"] == expected


@pytest.mark.parametrize("bad", ["[1, 2]", "42", '"a string"'])
def test_openai_compat_rejects_non_object_tool_arguments(monkeypatch, bad):
    from engine.providers.openai_compat import chat_completion

    assistant = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "open_app", "arguments": bad}}]}
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": assistant}]}
    monkeypatch.setattr("engine.providers.openai_compat.requests.post", MagicMock(return_value=response))

    result = chat_completion(base_url="https://example.test/v1", api_key="k", model="m", messages=[], provider_name="t", tools=[])
    assert result.ok is False
    assert result.error_code == "invalid_tool_arguments"
