"""UI adapter — entry point for Eel-exposed functions."""

import os
from core.config import cfg

_MAX_INPUT = 4000


def submit_text(text: str) -> dict:
    text = (text or "").strip()[:_MAX_INPUT]
    if not text:
        return {"status": "empty"}
    try:
        from core.dispatcher import submit_user_command
        submit_user_command(text, source="ui_text")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_env_status() -> dict:
    return {
        "groq": bool(cfg.groq_api_key),
        "gemini": bool(cfg.gemini_api_key),
    }


def get_runtime_status() -> dict:
    return {
        "mode": cfg.ui_mode,
        "brain_provider": cfg.brain_provider,
        "asr_provider": cfg.asr_provider,
        "tts_providers": cfg.tts_providers,
        "hotword_enabled": cfg.hotword_enabled,
        "clap_enabled": cfg.clap_enabled,
    }


def get_capabilities() -> dict:
    return {
        "file_drop": True,
        "hud_orb": True,
        "debug_log": True,
        "voice_input": True,
        "text_input": True,
    }


def get_tool_categories() -> list:
    return [
        {"id": "browser", "label": "Browser", "tools": ["new_tab", "close_tab", "history", "bookmarks"], "risk": "safe"},
        {"id": "apps", "label": "Applications", "tools": ["open_app", "close_app"], "risk": "safe"},
        {"id": "files", "label": "Files", "tools": ["create_folder", "create_file", "create_project"], "risk": "safe"},
        {"id": "system", "label": "System", "tools": ["volume_up", "volume_down", "screenshot", "time"], "risk": "safe"},
        {"id": "search", "label": "Search", "tools": ["web_search", "youtube_search", "find_places"], "risk": "safe"},
        {"id": "memory", "label": "Memory", "tools": ["remember", "forget", "recall", "notes"], "risk": "safe"},
    ]


def get_suggestions() -> list:
    return [
        {"label": "Open Chrome", "text": "open chrome", "category": "apps"},
        {"label": "Search Google", "text": "search ", "category": "search"},
        {"label": "Create Project", "text": "create project ", "category": "files"},
        {"label": "What time is it?", "text": "what time is it", "category": "system"},
        {"label": "Take Screenshot", "text": "take a screenshot", "category": "system"},
        {"label": "Play Music", "text": "play ", "category": "apps"},
        {"label": "Remember", "text": "remember that ", "category": "memory"},
        {"label": "Weather", "text": "what's the weather", "category": "search"},
    ]
