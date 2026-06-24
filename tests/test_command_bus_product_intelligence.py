import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _decision(route, intent, slots=None, confidence=0.95):
    return {
        "route": route,
        "intent": intent,
        "domain": "desktop" if intent == "open_app" else "conversation",
        "confidence": confidence,
        "slots": slots or {},
        "missing_slots": [],
        "expects_user_reply": False,
        "clarification_question": "",
        "risk_level": "none",
        "requires_confirmation": False,
        "reason": "test",
        "should_call_gemini": route == "brain",
        "should_call_tool": route == "tool",
    }


def test_tool_route_does_not_call_gemini(monkeypatch):
    import engine.command as command

    monkeypatch.setenv("NEXI_INTENT_V2_ENABLED", "true")
    with patch("engine.groq_intent_router_v2.route_intent_v2", return_value=_decision("tool", "open_app", {"app_name": "chrome"})), \
        patch("engine.tool_registry.execute_tool", return_value={"success": True, "verified": True, "message": "Opening chrome."}) as execute_tool, \
        patch("engine.command._safe_chatbot") as safe_chatbot, \
        patch("engine.command.speak"), \
        patch("engine.command.safe_eel_call"), \
        patch("engine.command._store_conversation_turn"):
        handled = command._handle_product_intelligence_v2("open chrome", "typed")

    assert handled is True
    safe_chatbot.assert_not_called()
    execute_tool.assert_called_once_with("open_app", {"app_name": "chrome"}, confirmed=False)


def test_brain_route_does_not_call_tool(monkeypatch):
    import engine.command as command

    monkeypatch.setenv("NEXI_INTENT_V2_ENABLED", "true")
    with patch("engine.groq_intent_router_v2.route_intent_v2", return_value=_decision("brain", "general_qa")), \
        patch("engine.tool_registry.execute_tool") as execute_tool, \
        patch("engine.command._safe_chatbot", return_value="brain answer") as safe_chatbot, \
        patch("engine.command.speak"), \
        patch("engine.command.safe_eel_call"), \
        patch("engine.command._store_conversation_turn"):
        handled = command._handle_product_intelligence_v2("what is ai", "typed")

    assert handled is True
    execute_tool.assert_not_called()
    safe_chatbot.assert_called_once_with("what is ai")


def test_product_tool_route_blocks_fake_success_without_verification(monkeypatch):
    import engine.command as command

    monkeypatch.setenv("NEXI_INTENT_V2_ENABLED", "true")
    unverified = {"success": True, "verified": False, "expects_user_reply": False, "message": "Done. Opened Chrome."}
    with patch("engine.groq_intent_router_v2.route_intent_v2", return_value=_decision("tool", "open_app", {"app_name": "chrome"})), \
        patch("engine.tool_registry.execute_tool", return_value=unverified), \
        patch("engine.command._safe_chatbot") as safe_chatbot, \
        patch("engine.command.speak") as speak, \
        patch("engine.command.safe_eel_call"), \
        patch("engine.command._store_conversation_turn"):
        handled = command._handle_product_intelligence_v2("open chrome", "typed")

    assert handled is True
    safe_chatbot.assert_not_called()
    assert "couldn't verify" in speak.call_args.args[0]
