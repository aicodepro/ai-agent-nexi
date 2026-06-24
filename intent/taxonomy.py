"""Intent taxonomy — all valid routes, intents, and validation."""

ROUTES = {
    "local_action", "brain", "workflow", "tool", "system",
    "greeting", "identity", "memory", "training", "output",
    "cancel", "followup", "reject", "clarify", "interrupt",
    "sleep", "repeat", "unknown", "jarvis",
}

BRAIN_INTENTS = {
    "general_qa", "explain", "summarize", "translate", "math",
    "code_help", "creative_writing", "essay", "analysis",
}

OUTPUT_INTENTS = {
    "copy_output", "save_output", "show_output", "close_output",
    "minimize_output", "pin_output", "create_file_from_output",
}

LOCAL_INTENTS = {
    "open_app", "open_website", "web_search", "youtube_search",
    "create_folder", "create_file", "create_project",
    "close_app", "volume_up", "volume_down", "zoom_in", "zoom_out",
    "new_tab", "close_tab", "next_tab", "prev_tab",
    "fullscreen", "minimize", "refresh", "go_back", "go_forward",
    "history", "bookmarks", "dev_tools", "private_window",
    "take_screenshot", "play_music", "get_time", "get_weather",
    "read_clipboard", "google_search", "send_email", "find_places",
    "set_reminder", "set_alarm", "show_reminders", "play_game",
    "start_hand_control", "start_eye_control", "stop_camera",
}

JARVIS_INTENTS: set[str] = {
    "run_agent", "execute_tool", "train_on_correction",
    "add_rule", "remove_rule", "agent_status",
    "reflect", "tool_help", "cancel_agent",
}

ALL_INTENTS = BRAIN_INTENTS | OUTPUT_INTENTS | LOCAL_INTENTS | JARVIS_INTENTS | {
    "greeting", "identity", "repeat", "sleep", "wake",
    "remember", "forget", "show_notes", "recall",
    "train_rule", "show_rules", "clear_rules", "explain_intent",
    "cancel_workflow", "run_plan", "list_tools", "unknown",
}


def empty_result() -> dict:
    return {"route": "unknown", "intent": "unknown", "confidence": 0.0,
            "entity": "", "reason": "no_match"}


def validate_route(route: str) -> str:
    return route if route in ROUTES else "unknown"


def validate_intent(intent: str) -> str:
    return intent if intent in ALL_INTENTS else "unknown"
