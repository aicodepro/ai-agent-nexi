"""Command dispatcher — the central command routing hub.

This replaces the 1914-line command.py with a clean, focused dispatcher.
Priority chain:
1. Workflow continuation
2. Clarification answer
3. Memory command
4. Intent routing → skill dispatch
5. Brain (LLM) fallback
"""

import re
import threading
from core.config import cfg
from core.tts import speak
from core.ui_state import emit_state

_local = threading.local()
_last_response = ""


def is_dispatching() -> bool:
    return getattr(_local, "dispatching", False)


def current_source() -> str:
    return getattr(_local, "source", "")


def normalize_command(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def submit_user_command(text: str, source: str = "ui_text", mode: str = "text") -> None:
    """Main entry point for all user commands from any source."""
    text = normalize_command(text)
    if not text:
        return

    _local.dispatching = True
    _local.source = source

    try:
        # Record turn in conversation context
        try:
            from memory.context import add_user_turn
            add_user_turn(text, source=source)
        except Exception:
            print(f"[DISPATCH] add_user_turn failed", flush=True)

        # Auto-extract memories
        try:
            from memory.manager import maybe_extract_memory
            maybe_extract_memory(text)
        except Exception:
            print(f"[DISPATCH] maybe_extract_memory failed", flush=True)

        # Infer user preferences
        try:
            from memory.user_model import infer_user_preference, update_user_model
            pref = infer_user_preference(text)
            if pref:
                update_user_model({"type": "preference", "text": text, "value": pref.get("value", "")})
        except Exception:
            print(f"[DISPATCH] infer_user_preference failed", flush=True)

        # Set UI state to thinking
        emit_state("thinking", source=source, text=text[:80])

        # Dispatch
        response = _dispatch(text, source)

        if response:
            _store_response(text, response, source)
            speak(response)

    except Exception as e:
        print(f"[DISPATCH] error reason={type(e).__name__}: {e}", flush=True)
        speak("Sorry, something went wrong.")
    finally:
        _local.dispatching = False
        _local.source = ""


def _dispatch(text: str, source: str, _depth: int = 0) -> str:
    """Priority-based dispatch chain."""

    # 0. Learned rule ("when I say X do Y") — execute the mapped action
    if _depth == 0:
        try:
            from memory.rules import match_rule
            action = match_rule(text)
            if action:
                return _dispatch(action, source, _depth=1)
        except Exception:
            print(f"[DISPATCH] match_rule failed", flush=True)

    # 1. Active workflow
    try:
        from workflow.manager import handle_active_workflow
        result = handle_active_workflow(text)
        if result:
            return result
    except Exception:
        print(f"[DISPATCH] workflow failed", flush=True)

    # 2. Pending clarification
    try:
        from workflow.clarification import has_pending, receive_answer
        if has_pending():
            answer = receive_answer(text)
            if answer.get("handled"):
                return _handle_clarification_answer(answer)
    except Exception:
        print(f"[DISPATCH] clarification failed", flush=True)

    # 3. Memory commands
    try:
        from memory.manager import parse_memory_command
        result = parse_memory_command(text)
        if result.get("handled"):
            return result.get("response", "Done.")
    except Exception:
        print(f"[DISPATCH] memory command failed", flush=True)

    # 4. Intent routing
    from intent.router import route_intent
    intent_result = route_intent(text)
    route = intent_result.get("route", "unknown")
    intent = intent_result.get("intent", "unknown")
    entity = intent_result.get("entity", "")
    confidence = intent_result.get("confidence", 0.0)

    # Handle by route type
    if route == "greeting":
        return _greeting_response()

    if route == "identity":
        return f"I'm {cfg.name}, your AI assistant. I can help with apps, searches, files, and questions."

    if route == "sleep":
        emit_state("sleep")
        return "Going to sleep. Say my name when you need me."

    if route == "system" and intent == "repeat":
        return _last_response or "I haven't said anything yet."

    if route == "system" and intent == "wake":
        emit_state("listening")
        return "I'm here! How can I help?"

    if route == "cancel":
        try:
            from workflow.manager import clear_workflow
            clear_workflow()
        except Exception:
            print(f"[DISPATCH] clear_workflow failed", flush=True)
        return "Cancelled."

    if route == "output":
        return _handle_output_intent(intent)

    if route == "training":
        return _handle_training_intent(intent, entity)

    if route == "workflow" and intent == "run_plan":
        from brain.planner import run_plan
        return run_plan(entity)

    if route == "brain" and intent == "explain_intent":
        return "I can help explain things. What would you like me to explain?"

    # Handle local_action intents that have no dedicated skill handler
    if route == "local_action" and intent in ("save_output", "copy_output", "append_output"):
        return _handle_output_intent(intent)


    if route == "tool":
        return _handle_tool_intent(intent, entity)

    if route == "jarvis":
        if not cfg.jarvis.jarvis_enabled:
            return "Jarvis features are disabled in configuration."
        from skills.dispatch import handle_skill
        result = handle_skill(intent, entity)
        return result.get("message", "Jarvis handler executed. Full implementation coming in later phases.")

    # 5. Local action → skill dispatch
    if route == "local_action" and confidence >= 0.7:
        from skills.dispatch import handle_skill
        result = handle_skill(intent, entity)
        if result.get("handled"):
            return result.get("message", "Done.")

    # 6. Clarification for ambiguous commands
    if route == "clarify" or (route == "unknown" and len(text.split()) <= 2):
        try:
            from workflow.clarification import ask_clarification
            clar = ask_clarification(text)
            if clar:
                return clar["question"]
        except Exception:
            print(f"[DISPATCH] ask_clarification failed", flush=True)

    # 7. Brain (LLM) fallback
    if route in {"brain", "unknown"} or confidence < 0.5:
        try:
            from brain.gemini import ask_brain
            return ask_brain(text)
        except Exception as e:
            return f"I couldn't process that: {type(e).__name__}"

    # 8. Try skill as last resort
    from skills.dispatch import handle_skill
    result = handle_skill(intent, entity)
    if result.get("handled"):
        return result.get("message", "Done.")

    return "I'm not sure what you mean. Could you rephrase?"


def _store_response(user_text: str, response: str, source: str):
    global _last_response
    _last_response = response
    try:
        from memory.context import add_assistant_turn
        add_assistant_turn(response, source=source)
    except Exception:
        print(f"[DISPATCH] store_response add_assistant_turn failed", flush=True)
    try:
        from memory.manager import maybe_extract_memory
        maybe_extract_memory(user_text, response)
    except Exception:
        print(f"[DISPATCH] store_response extract_memory failed", flush=True)


def _greeting_response() -> str:
    import datetime
    hour = datetime.datetime.now().hour
    if hour < 12:
        return f"Good morning! I'm {cfg.name}. How can I help?"
    elif hour < 18:
        return f"Good afternoon! I'm {cfg.name}. How can I help?"
    return f"Good evening! I'm {cfg.name}. How can I help?"


def _handle_output_intent(intent: str) -> str:
    if intent in ("copy_output", "copy"):
        try:
            from memory.context import get_last_assistant_response
            text = get_last_assistant_response()
            if text:
                import pyperclip
                pyperclip.copy(text)
                return "Copied to clipboard."
            return "Nothing to copy."
        except Exception:
            return "Couldn't copy."
    if intent in ("save_output", "save"):
        try:
            from memory.context import get_last_assistant_response
            text = get_last_assistant_response()
            if text:
                from datetime import datetime
                from pathlib import Path
                desktop = Path.home() / "Desktop"
                desktop.mkdir(parents=True, exist_ok=True)
                fname = desktop / f"nexi_output_{datetime.now():%Y%m%d_%H%M%S}.txt"
                fname.write_text(text, encoding="utf-8")
                return f"Saved to {fname.name}"
            return "Nothing to save."
        except Exception:
            return "Couldn't save."
    if intent in ("append_output",):
        return "Append not yet supported."
    return "Output action not available."

def _handle_training_intent(intent: str, entity: str) -> str:
    if intent == "train_rule":
        try:
            from memory.rules import learn_rule
            return learn_rule(entity)
        except Exception:
            return "Couldn't save rule."
    if intent == "show_rules":
        try:
            from memory.rules import list_rules
            rules = list_rules()
            if rules:
                return "Rules:\n" + "\n".join(
                    f"- when I say '{r['trigger']}' -> {r['action']}" for r in rules)
            return "No rules saved."
        except Exception:
            return "Couldn't load rules."
    if intent == "clear_rules":
        try:
            from memory.rules import clear_rules
            n = clear_rules()
            return f"Cleared {n} rule{'s' if n != 1 else ''}."
        except Exception:
            return "Couldn't clear rules."
    return "Unknown training command."


def _handle_tool_intent(intent: str, entity: str) -> str:
    if intent == "list_tools":
        try:
            from tools.mcp import list_tools
            tools = list_tools()
            if not tools:
                return "No MCP servers are configured."
            lines = []
            for server, names in tools.items():
                lines.append(f"{server}: {', '.join(names) if names else '(none)'}")
            return "Available tools:\n" + "\n".join(lines)
        except Exception:
            return "Couldn't list tools."
    return "Tool action not available."


def _handle_clarification_answer(answer: dict) -> str:
    text = answer.get("answer", "")
    followup_type = answer.get("followup_type", "")

    intent_map = {
        "open_app": "open_app", "web_search": "web_search",
        "play_music": "play_music", "find_places": "find_places",
        "close_app": "close_app", "create_file": "create_file",
    }

    intent = intent_map.get(followup_type, "")
    if intent:
        from skills.dispatch import handle_skill
        result = handle_skill(intent, text)
        if result.get("handled"):
            return result.get("message", "Done.")

    return f"I'll try: {text}"
