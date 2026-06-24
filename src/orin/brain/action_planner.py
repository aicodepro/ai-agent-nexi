from src.orin.control.registry import ControlRegistry


INTENT_ACTION_MAP = {
    "control_open_chrome": {"skill": "browser", "function": "open_chrome"},
    "control_open_url": {"skill": "browser", "function": "open_url"},
    "control_open_youtube": {"skill": "browser", "function": "open_youtube"},
    "control_search_youtube": {"skill": "browser", "function": "search_youtube"},
    "control_search_google": {"skill": "browser", "function": "search_google"},
    "control_new_tab": {"skill": "browser", "function": "new_tab"},
    "control_close_tab": {"skill": "browser", "function": "close_tab"},
    "control_tab_info": {"skill": "browser", "function": "get_tab_info"},
    "control_show_apps": {"skill": "desktop", "function": "list_apps"},
    "control_focus_app": {"skill": "desktop", "function": "focus_app"},
    "control_active_window": {"skill": "desktop", "function": "get_active_window"},
    "control_create_folder": {"skill": "files", "function": "create_folder"},
    "control_open_folder": {"skill": "files", "function": "open_folder"},
    "control_emergency_stop": {"skill": "system", "function": "emergency_stop"},
    "control_status": {"skill": "system", "function": "list_control_actions"},
    "open_app": {"skill": "desktop", "function": "open_app"},
    "close_app": {"skill": "desktop", "function": "close_app"},
    "youtube": {"skill": "browser", "function": "search_youtube"},
    "search_google": {"skill": "browser", "function": "search_google"},
    "diagnose_jarvi": {"skill": "diagnostics", "function": "diagnose"},
    "check_hotword": {"skill": "diagnostics", "function": "check_hotword"},
    "check_bridge": {"skill": "diagnostics", "function": "check_bridge"},
    "check_playwright": {"skill": "diagnostics", "function": "check_playwright"},
}

RISK_MAP = {
    "open_chrome": "MEDIUM",
    "open_url": "MEDIUM",
    "open_youtube": "MEDIUM",
    "search_youtube": "MEDIUM",
    "search_google": "MEDIUM",
    "new_tab": "SAFE",
    "close_tab": "MEDIUM",
    "get_tab_info": "SAFE",
    "list_apps": "SAFE",
    "focus_app": "MEDIUM",
    "get_active_window": "SAFE",
    "create_folder": "MEDIUM",
    "open_folder": "MEDIUM",
    "open_app": "MEDIUM",
    "close_app": "HIGH",
    "emergency_stop": "SAFE",
    "list_control_actions": "SAFE",
    "diagnose": "SAFE",
    "check_hotword": "SAFE",
    "check_bridge": "SAFE",
    "check_playwright": "SAFE",
}


class ActionPlanner:
    @classmethod
    def plan(cls, intent_name, entities=None, confidence=0.0, corrected_query=""):
        mapping = INTENT_ACTION_MAP.get(intent_name, {})
        skill = mapping.get("skill", "unknown")
        function = mapping.get("function", "")
        risk = RISK_MAP.get(function, "MEDIUM")
        steps = []
        if function:
            steps.append({"action": function, "skill": skill})
        missing = []
        if function in ("open_url",) and not (entities or {}).get("url"):
            missing.append("url")
        if function in ("search_youtube", "search_google") and not (entities or {}).get("query"):
            missing.append("query")
        if function in ("open_app", "focus_app", "close_app") and not (entities or {}).get("app_name"):
            missing.append("app_name")
        if function in ("create_folder",) and not (entities or {}).get("folder_name"):
            missing.append("folder_name")
        requires_follow_up = len(missing) > 0
        follow_up = ""
        if missing:
            follow_up = f"What {' is '.join(missing) }?" if len(missing) == 1 else f"Please provide: {', '.join(missing)}"
        return {
            "intent": intent_name,
            "skill": skill,
            "function": function,
            "confidence": confidence,
            "risk_level": risk,
            "privacy_sensitivity": "MEDIUM" if risk in ("HIGH", "CRITICAL") else "LOW",
            "requires_confirmation": risk in ("HIGH", "CRITICAL"),
            "requires_follow_up": requires_follow_up,
            "follow_up_question": follow_up,
            "missing_fields": missing,
            "steps": steps,
            "entities": entities or {},
        }
