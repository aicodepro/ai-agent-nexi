"""Unified intent router — deterministic first, Groq LLM fallback."""

import json
import os
import re
from intent.taxonomy import (
    ROUTES, BRAIN_INTENTS, OUTPUT_INTENTS, LOCAL_INTENTS,
    empty_result, validate_route, validate_intent,
)

# --- Deterministic patterns ---

_GREETINGS = {"hi", "hello", "hey", "good morning", "good afternoon",
              "good evening", "howdy", "what's up", "whats up", "sup"}
_IDENTITY = {"who are you", "what are you", "what is your name",
             "what's your name", "whats your name", "tell me about yourself"}
_CANCEL = {"cancel", "stop", "never mind", "nevermind", "exit", "quit", "forget it", "leave it"}

_LOCAL_PREFIXES = [
    ("open ", "open_app"), ("launch ", "open_app"), ("start ", "open_app"),
    ("close ", "close_app"), ("search ", "web_search"), ("google ", "google_search"),
    ("play ", "play_music"), ("create folder", "create_folder"),
    ("create a folder", "create_folder"), ("make a folder", "create_folder"),
    ("create file", "create_file"), ("create a file", "create_file"),
    ("create project", "create_project"), ("create a project", "create_project"),
    ("go to ", "open_website"), ("visit ", "open_website"),
    ("take screenshot", "take_screenshot"), ("take a screenshot", "take_screenshot"),
    ("save note", "save_note"), ("send email", "send_email"),
    ("find ", "find_places"), ("where is", "find_places"),
    ("youtube ", "youtube_search"), ("play on youtube", "youtube_search"),
]

_LOCAL_EXACT = {
    "volume up": "volume_up", "volume down": "volume_down",
    "increase volume": "volume_up", "decrease volume": "volume_down",
    "mute": "volume_down", "zoom in": "zoom_in", "zoom out": "zoom_out",
    "new tab": "new_tab", "close tab": "close_tab",
    "next tab": "next_tab", "previous tab": "prev_tab",
    "full screen": "fullscreen", "fullscreen": "fullscreen",
    "minimize": "minimize", "refresh": "refresh",
    "go back": "go_back", "go forward": "go_forward",
    "history": "history", "bookmarks": "bookmarks",
    "developer tools": "dev_tools", "dev tools": "dev_tools",
    "private window": "private_window", "incognito": "private_window",
    "what time is it": "get_time", "time": "get_time",
    "what's the time": "get_time", "current time": "get_time",
    "read clipboard": "read_clipboard", "read selected": "read_clipboard",
    "what's the weather": "get_weather", "weather": "get_weather",
}

_QA_PREFIXES = [
    "what ", "who ", "where ", "when ", "why ", "how ",
    "can you ", "could you ", "tell me ", "explain ",
    "describe ", "define ", "summarize ", "translate ",
    "write ", "generate ", "compose ", "draft ",
    "help me ", "give me ", "list ", "compare ",
    "analyze ", "calculate ",
]

_MEMORY_PATTERNS = [
    (r"^remember\s+(that\s+)?", "remember"),
    (r"^forget\s+", "forget"),
    (r"^show\s+(my\s+)?notes", "show_notes"),
    (r"^what do you (know|remember)", "recall"),
    (r"^recall\s+", "recall"),
]

_TRAINING_PATTERNS = [
    (r"^when i say .+,?\s*(do|open|run|execute)", "train_rule"),
    (r"^learn\s+(that|this)", "train_rule"),
    (r"^show\s+(my\s+)?rules", "show_rules"),
    (r"^clear\s+(all\s+)?rules", "clear_rules"),
]

_MATH_RE = re.compile(r"^[\d\s\+\-\*/\(\)\.\^%]+$")

_OUTPUT_PATTERNS = [
    (r"^copy\s+(it|that|this|output|code|result)", "copy_output"),
    (r"^save\s+(it|that|this|output|code|result)", "save_output"),
    (r"^show\s+(it|that|this|output|code|result)", "show_output"),
    (r"^close\s+(output|workspace|panel)", "close_output"),
    (r"^create\s+file\s+from\s+(output|that|this)", "create_file_from_output"),
]

_REPEAT_PATTERNS = {"repeat", "say that again", "repeat that", "what did you say",
                    "come again", "say again", "one more time"}

_SLEEP_PATTERNS = {"go to sleep", "sleep", "good night", "bye", "goodbye",
                   "shut up", "stop listening", "see you later"}
_WAKE_PATTERNS = {"wake up", "i'm back", "im back", "hey nexi", "nexi"}


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.strip().lower())


def _result(route: str, intent: str, confidence: float, entity: str = "",
            reason: str = "deterministic") -> dict:
    return {"route": validate_route(route), "intent": validate_intent(intent),
            "confidence": confidence, "entity": entity, "reason": reason}


def _deterministic(text: str) -> dict:
    n = _norm(text)

    # Sleep/wake
    if n in _SLEEP_PATTERNS:
        return _result("sleep", "sleep", 1.0)
    if n in _WAKE_PATTERNS:
        return _result("system", "wake", 1.0)

    # Cancel
    if n in _CANCEL:
        return _result("cancel", "cancel_workflow", 1.0)

    # Repeat
    if n in _REPEAT_PATTERNS:
        return _result("system", "repeat", 1.0)

    # Greetings
    if n in _GREETINGS:
        return _result("greeting", "greeting", 1.0)

    # Identity
    if n in _IDENTITY:
        return _result("identity", "identity", 1.0)

    # Output actions
    for pattern, intent in _OUTPUT_PATTERNS:
        if re.match(pattern, n):
            return _result("output", intent, 0.95)

    # Memory
    for pattern, intent in _MEMORY_PATTERNS:
        if re.match(pattern, n):
            entity = re.sub(pattern, "", n).strip()
            return _result("memory", intent, 0.95, entity=entity)

    # Training
    for pattern, intent in _TRAINING_PATTERNS:
        if re.match(pattern, n):
            return _result("training", intent, 0.95, entity=text.strip())

    # Exact local commands
    if n in _LOCAL_EXACT:
        return _result("local_action", _LOCAL_EXACT[n], 1.0)

    # Prefix-based local commands
    for prefix, intent in _LOCAL_PREFIXES:
        if n.startswith(prefix):
            entity = text.strip()[len(prefix):].strip()
            return _result("local_action", intent, 0.9, entity=entity)

    # Math
    if _MATH_RE.match(n) and len(n) >= 3:
        return _result("brain", "math", 0.95, entity=text.strip())

    # Q&A prefixes → brain
    for prefix in _QA_PREFIXES:
        if n.startswith(prefix):
            return _result("brain", "general_qa", 0.7, entity=text.strip())

    return empty_result()


def _route_with_groq(text: str) -> dict:
    """LLM-based routing when deterministic fails."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return empty_result()

    model = os.getenv("GROQ_INTENT_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "intent_router_prompt.txt")
    system_prompt = ""
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()
    except FileNotFoundError:
        system_prompt = (
            "Classify the user intent. Return JSON: {\"route\": \"...\", \"intent\": \"...\", "
            "\"confidence\": 0.0-1.0, \"entity\": \"...\"}. "
            "Routes: local_action, brain, greeting, identity, memory, training, output, sleep, system, unknown. "
            "Only return valid JSON."
        )

    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": 150,
            },
            timeout=8,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Extract JSON from response
        match = re.search(r"\{[^}]+\}", content)
        if match:
            data = json.loads(match.group())
            return {
                "route": validate_route(data.get("route", "unknown")),
                "intent": validate_intent(data.get("intent", "unknown")),
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                "entity": str(data.get("entity", "")),
                "reason": "groq_llm",
            }
    except Exception as e:
        print(f"[INTENT] groq_failed reason={type(e).__name__}", flush=True)

    return empty_result()


def route_intent(text: str) -> dict:
    """Route user text to an intent. Deterministic first, Groq LLM fallback."""
    if not text or not text.strip():
        return empty_result()

    result = _deterministic(text)
    if result["confidence"] >= 0.7:
        return result

    llm_result = _route_with_groq(text)
    if llm_result["confidence"] > result["confidence"]:
        return llm_result

    # If both are low, default to brain for anything that looks like a question
    if result["route"] == "unknown" and len(text.split()) >= 3:
        return _result("brain", "general_qa", 0.4, entity=text.strip(), reason="fallback_to_brain")

    return result
