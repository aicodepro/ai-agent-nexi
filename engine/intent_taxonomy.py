from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "2.0"

SCHEMA_FIELDS = (
    "schema_version",
    "route",
    "intent",
    "domain",
    "confidence",
    "slots",
    "missing_slots",
    "expects_user_reply",
    "clarification_question",
    "risk_level",
    "requires_confirmation",
    "reason",
    "should_call_gemini",
    "should_call_tool",
)

ALLOWED_ROUTES = {
    "interrupt",
    "sleep",
    "wake",
    "clarify",
    "followup",
    "workflow",
    "tool",
    "memory",
    "training",
    "output",
    "brain",
    "react",
    "system",
    "reject",
    "cancel",
}

ALLOWED_DOMAINS = {
    "desktop",
    "browser",
    "web",
    "memory",
    "training",
    "output",
    "workflow",
    "conversation",
    "system",
    "unknown",
}

ALLOWED_RISK_LEVELS = {"none", "low", "medium", "high", "critical"}

ALLOWED_INTENTS = {
    "unknown",
    "clarify",
    "stop_speaking",
    "cancel",
    "sleep",
    "wake",
    "greeting",
    "identity",
    "repeat_last",
    "system_status",
    "confirmation",
    "continue_response",
    "open_app",
    "open_website",
    "web_search",
    "create_folder",
    "create_project_folder",
    "create_file",
    "take_screenshot",
    "take_note",
    "show_notes",
    "remember",
    "recall_memory",
    "forget_memory",
    "open_output_workspace",
    "close_output_workspace",
    "minimize_output_workspace",
    "pin_output_workspace",
    "copy_latest_output",
    "save_latest_output",
    "create_file_from_latest_output",
    "show_latest_output",
    "read_output_summary",
    "shorten_latest_output",
    "regenerate_latest_output",
    "volume_up",
    "volume_down",
    "mute",
    "clipboard_read",
    "clipboard_write_safe",
    "camera_preview",
    "hand_gesture_control",
    "eye_mouse_control",
    "stop_camera_control",
    "gesture_click_mode",
    "gesture_scroll_mode",
    "eye_mouse_calibrate",
    "search_youtube",
    "play_youtube",
    "tell_time",
    "tell_joke",
    "weather_lookup",
    "internet_speed_test",
    "get_active_window",
    "what_am_i_working_on",
    "get_system_state",
    "why_is_pc_slow",
    "am_i_online",
    "get_network_status",
    "get_ip_address",
    "get_disk_space",
    "is_disk_full",
    "get_battery_status",
    "get_running_apps",
    "get_idle_time",
    "open_settings",
    "open_wifi_settings",
    "open_bluetooth_settings",
    "open_display_settings",
    "open_sound_settings",
    "open_microphone_settings",
    "open_camera_settings",
    "open_startup_settings",
    "open_windows_update",
    "open_settings_page",
    "show_diagnostics",
    "get_monitor_state",
    "echo_guard_status",
    "get_hud_state",
    "resolve_app_for_task",
    "open_app_for_task",
    "what_did_you_learn",
    "list_skills",
    "describe_skill",
    "read_current_page",
    "list_browser_tabs",
    "read_browser_console",
    "media_pause",
    "media_resume",
    "media_mute",
    "browser_new_tab",
    "browser_close_tab",
    "browser_refresh",
    "browser_back",
    "browser_forward",
    "browser_history",
    "browser_fullscreen",
    "general_qa",
    "essay_request",
    "summarize",
    "explain",
    "workflow_answer",
    "workflow_switch",
    "react_multi_step",
    "train_nexi",
    "learn_rule",
    "correction",
    "training_answer",
    "show_training_rules",
    "show_training_profiles",
    "cognitive_status",
    "learned_rule_match",
    "user_preference_update",
    "why_did_you_do_that",
    "what_did_you_understand",
    "train_need_profile",
    "start_ultra_training",
    "deep_training_command",
}

TOOL_INTENTS = {
    "open_app",
    "open_website",
    "web_search",
    "create_folder",
    "create_project_folder",
    "create_file",
    "take_screenshot",
    "take_note",
    "show_notes",
    "remember",
    "recall_memory",
    "forget_memory",
    "open_output_workspace",
    "close_output_workspace",
    "minimize_output_workspace",
    "pin_output_workspace",
    "copy_latest_output",
    "save_latest_output",
    "create_file_from_latest_output",
    "show_latest_output",
    "read_output_summary",
    "shorten_latest_output",
    "regenerate_latest_output",
    "volume_up",
    "volume_down",
    "mute",
    "clipboard_read",
    "clipboard_write_safe",
    "camera_preview",
    "hand_gesture_control",
    "eye_mouse_control",
    "stop_camera_control",
    "gesture_click_mode",
    "gesture_scroll_mode",
    "eye_mouse_calibrate",
    "search_youtube",
    "play_youtube",
    "tell_time",
    "tell_joke",
    "weather_lookup",
    "internet_speed_test",
    "get_active_window",
    "what_am_i_working_on",
    "get_system_state",
    "why_is_pc_slow",
    "am_i_online",
    "get_network_status",
    "get_ip_address",
    "get_disk_space",
    "is_disk_full",
    "get_battery_status",
    "get_running_apps",
    "get_idle_time",
    "open_settings",
    "open_wifi_settings",
    "open_bluetooth_settings",
    "open_display_settings",
    "open_sound_settings",
    "open_microphone_settings",
    "open_camera_settings",
    "open_startup_settings",
    "open_windows_update",
    "open_settings_page",
    "show_diagnostics",
    "get_monitor_state",
    "echo_guard_status",
    "get_hud_state",
    "resolve_app_for_task",
    "open_app_for_task",
    "what_did_you_learn",
    "list_skills",
    "describe_skill",
    "read_current_page",
    "list_browser_tabs",
    "read_browser_console",
    "media_pause",
    "media_resume",
    "media_mute",
    "browser_new_tab",
    "browser_close_tab",
    "browser_refresh",
    "browser_back",
    "browser_forward",
    "browser_history",
    "browser_fullscreen",
}

OUTPUT_INTENTS = {
    "open_output_workspace",
    "close_output_workspace",
    "minimize_output_workspace",
    "pin_output_workspace",
    "copy_latest_output",
    "save_latest_output",
    "create_file_from_latest_output",
    "show_latest_output",
    "read_output_summary",
    "shorten_latest_output",
    "regenerate_latest_output",
}

BRAIN_INTENTS = {"general_qa", "essay_request", "summarize", "explain", "continue_response"}


def clamp_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def empty_result(
    *,
    route: str = "clarify",
    intent: str = "unknown",
    domain: str = "unknown",
    confidence: float = 0.0,
    reason: str = "default",
    clarification_question: str = "I didn't catch that. Please say it again in English.",
) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "route": route if route in ALLOWED_ROUTES else "clarify",
        "intent": intent if intent in ALLOWED_INTENTS else "unknown",
        "domain": domain if domain in ALLOWED_DOMAINS else "unknown",
        "confidence": clamp_confidence(confidence),
        "slots": {},
        "missing_slots": [],
        "expects_user_reply": route == "clarify",
        "clarification_question": clarification_question if route == "clarify" else "",
        "risk_level": "none",
        "requires_confirmation": False,
        "reason": str(reason or "default")[:240],
        "should_call_gemini": route == "brain",
        "should_call_tool": route == "tool",
    }
    return exact_schema(result)


def router_decision_schema() -> dict[str, Any]:
    """JSON Schema for provider structured-output router decisions.

    Mirrors the canonical decision shape so a provider that supports
    response_format=json_schema returns a result we can validate directly.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "route": {"type": "string", "enum": sorted(ALLOWED_ROUTES)},
            "intent": {"type": "string", "enum": sorted(ALLOWED_INTENTS)},
            "domain": {"type": "string", "enum": sorted(ALLOWED_DOMAINS)},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "slots": {"type": "object", "additionalProperties": True},
            "missing_slots": {"type": "array", "items": {"type": "string"}},
            "expects_user_reply": {"type": "boolean"},
            "clarification_question": {"type": "string"},
            "risk_level": {"type": "string", "enum": sorted(ALLOWED_RISK_LEVELS)},
            "requires_confirmation": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["route", "intent", "confidence", "slots", "missing_slots", "risk_level", "requires_confirmation", "reason"],
    }


def exact_schema(value: dict[str, Any] | None) -> dict[str, Any]:
    source = value or {}
    result = {field: source.get(field) for field in SCHEMA_FIELDS}
    result["schema_version"] = SCHEMA_VERSION
    result["route"] = result.get("route") if result.get("route") in ALLOWED_ROUTES else "clarify"
    result["intent"] = result.get("intent") if result.get("intent") in ALLOWED_INTENTS else "unknown"
    result["domain"] = result.get("domain") if result.get("domain") in ALLOWED_DOMAINS else "unknown"
    result["confidence"] = clamp_confidence(result.get("confidence"))
    result["slots"] = result.get("slots") if isinstance(result.get("slots"), dict) else {}
    missing = result.get("missing_slots")
    result["missing_slots"] = [str(item) for item in missing] if isinstance(missing, list) else []
    result["expects_user_reply"] = bool(result.get("expects_user_reply"))
    result["clarification_question"] = str(result.get("clarification_question") or "")[:300]
    result["risk_level"] = result.get("risk_level") if result.get("risk_level") in ALLOWED_RISK_LEVELS else "none"
    result["requires_confirmation"] = bool(result.get("requires_confirmation"))
    result["reason"] = str(result.get("reason") or "")[:240]
    route = result["route"]
    result["should_call_gemini"] = route == "brain"
    result["should_call_tool"] = route == "tool"
    if route == "clarify":
        result["expects_user_reply"] = True
        if not result["clarification_question"]:
            result["clarification_question"] = "I didn't catch that. Please say it again in English."
    elif route not in {"followup", "workflow"}:
        result["expects_user_reply"] = False
    return result
