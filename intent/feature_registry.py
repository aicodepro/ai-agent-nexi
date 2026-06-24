"""Dynamic feature registry — the intent router's knowledge of what NEXI can do.

The feature list is derived at runtime from the actually-registered skills
(`skills.dispatch.SKILL_MAP`) plus the taxonomy, so adding a new skill
automatically teaches the LLM router about it. There are no hardcoded
phrase -> intent mappings here; the model decides, this only tells it the
menu of real, dispatchable features.
"""

from __future__ import annotations

from intent.taxonomy import LOCAL_INTENTS, BRAIN_INTENTS, OUTPUT_INTENTS, JARVIS_INTENTS

_DESCRIPTIONS = {
    "open_app": "open a desktop application (chrome, notepad, spotify, ...)",
    "close_app": "close a running application",
    "open_website": "open a website in the browser",
    "web_search": "search the web for something",
    "google_search": "search Google for something",
    "youtube_search": "search or play something on YouTube",
    "get_time": "tell the current time",
    "get_weather": "report the weather",
    "read_clipboard": "read the clipboard contents aloud",
    "play_music": "play music",
    "take_screenshot": "take a screenshot",
    "create_folder": "create a folder",
    "create_file": "create a file",
    "create_project": "scaffold a code project",
    "send_email": "send an email",
    "find_places": "find places or locations on a map",
    "set_reminder": "set a reminder",
    "set_alarm": "set an alarm",
    "show_reminders": "list reminders",
    "play_game": "play rock paper scissors",
    "start_hand_control": "control the mouse with hand gestures",
    "start_eye_control": "control the mouse with eye or face tracking",
    "stop_camera": "stop camera-based control",
    "volume_up": "increase the volume",
    "volume_down": "decrease the volume",
    "zoom_in": "zoom in",
    "zoom_out": "zoom out",
    "new_tab": "open a new browser tab",
    "close_tab": "close the current browser tab",
    "next_tab": "switch to the next browser tab",
    "prev_tab": "switch to the previous browser tab",
    "fullscreen": "toggle fullscreen",
    "minimize": "minimize the window",
    "refresh": "refresh the page",
    "go_back": "navigate back",
    "go_forward": "navigate forward",
    "history": "open browser history",
    "bookmarks": "open bookmarks",
    "dev_tools": "open developer tools",
    "private_window": "open a private window",
    "general_qa": "answer a general question, explain, or chat",
    "run_agent": "run a multi-step agent task",
    "execute_tool": "run a specific named tool",
    "agent_status": "show NEXI agent system status",
    "cancel_agent": "cancel a running agent",
    "train_on_correction": "learn from a correction",
    "add_rule": "add a custom behaviour rule",
    "remove_rule": "remove a custom rule",
    "reflect": "reflect on recent interactions",
    "tool_help": "explain how to use a tool",
}


def route_for(intent: str) -> str:
    """Derive the dispatch route for an intent from the taxonomy."""
    if intent in LOCAL_INTENTS:
        return "local_action"
    if intent in JARVIS_INTENTS:
        return "jarvis"
    if intent in OUTPUT_INTENTS:
        return "output"
    if intent in BRAIN_INTENTS:
        return "brain"
    return "local_action"


def discover_features() -> list[dict]:
    """Introspect the dispatchable skills + general Q&A into a feature list.

    Only features the dispatcher can actually execute after an LLM decision
    are exposed, so the model can never route to a dead end.
    """
    from skills.dispatch import SKILL_MAP

    intents = set(SKILL_MAP.keys()) | {"general_qa"}
    features = []
    for intent in sorted(intents):
        features.append({
            "intent": intent,
            "route": route_for(intent),
            "description": _DESCRIPTIONS.get(intent, intent.replace("_", " ")),
        })
    return features


def build_router_prompt() -> str:
    """Build the LLM router system prompt dynamically from real features."""
    features = discover_features()
    lines = [
        "You are NEXI's intent router. The user's text may be partially misheard "
        "by speech recognition; infer their true intent and map it to exactly ONE "
        "feature from the list below.",
        "",
        'Return STRICT JSON only: {"route": "...", "intent": "...", '
        '"confidence": 0.0-1.0, "entity": "..."}',
        "  - route and intent MUST be copied exactly from a list row.",
        '  - entity = the argument (app name, search query, ...) or "".',
        '  - If nothing fits, return {"route": "brain", "intent": "general_qa", '
        '"confidence": 0.5, "entity": "<the text>"}.',
        "",
        "Available features (intent | route | what it does):",
    ]
    for f in features:
        lines.append(f"- {f['intent']} | {f['route']} | {f['description']}")
    return "\n".join(lines)
