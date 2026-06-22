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
            pass

        # Auto-extract memories
        try:
            from memory.manager import maybe_extract_memory
            maybe_extract_memory(text)
        except Exception:
            pass

        # Infer user preferences
        try:
            from memory.user_model import infer_user_preference, update_user_model
            pref = infer_user_preference(text)
            if pref:
                update_user_model({"type": "preference", "text": text, "value": pref.get("value", "")})
        except Exception:
            pass

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


def _dispatch(text: str, source: str) -> str:
    """Priority-based dispatch chain."""

    # 1. Active workflow
    try:
        from workflow.manager import handle_active_workflow
        result = handle_active_workflow(text)
        if result:
            return result
    except Exception:
        pass

    # 2. Pending clarification
    try:
        from workflow.clarification import has_pending, receive_answer
        if has_pending():
            answer = receive_answer(text)
            if answer.get("handled"):
                return _handle_clarification_answer(answer)
    except Exception:
        pass

    # 3. Memory commands
    try:
        from memory.manager import parse_memory_command
        result = parse_memory_command(text)
        if result.get("handled"):
            return result.get("response", "Done.")
    except Exception:
        pass

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
            pass
        return "Cancelled."

    if route == "output":
        return _handle_output_intent(intent)

    if route == "training":
        return _handle_training_intent(intent, entity)

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
            pass

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
        pass
    try:
        from memory.manager import maybe_extract_memory
        maybe_extract_memory(user_text, response)
    except Exception:
        pass


def _greeting_response() -> str:
    import datetime
    hour = datetime.datetime.now().hour
    if hour < 12:
        return f"Good morning! I'm {cfg.name}. How can I help?"
    elif hour < 18:
        return f"Good afternoon! I'm {cfg.name}. How can I help?"
    return f"Good evening! I'm {cfg.name}. How can I help?"


def _handle_output_intent(intent: str) -> str:
    if intent == "copy_output":
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
    return "Output action not available."


def _handle_training_intent(intent: str, entity: str) -> str:
    if intent == "train_rule":
        try:
            from memory.manager import remember
            return remember(entity, category="rules", source="training")
        except Exception:
            return "Couldn't save rule."
    if intent == "show_rules":
        try:
            from memory.manager import recall
            rules = [i for i in recall(limit=20) if i.get("category") == "rules"]
            if rules:
                return "Rules:\n" + "\n".join(f"- {r['text'][:80]}" for r in rules)
            return "No rules saved."
        except Exception:
            return "Couldn't load rules."
    if intent == "clear_rules":
        try:
            from memory.manager import forget
            forget("")  # This won't clear all — intentional safety
            return "Rules cleared."
        except Exception:
            return "Couldn't clear rules."
    return "Unknown training command."


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
