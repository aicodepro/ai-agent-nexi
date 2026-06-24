import os
import sys
from unittest.mock import patch

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
    monkeypatch.setattr(ReActPlanner, "_call_llm", lambda self, messages, tools_schema: next(calls))
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
        lambda self, messages, tools_schema: {"action": "tool_call", "tool_name": "clipboard_write_safe", "tool_input": {"text": "hello"}},
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
