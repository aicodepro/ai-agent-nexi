# tool_category_view.py
#
# Exposes safe tool categories from Nexi tool_registry for the Mark-style UI.
# Never exposes dangerous tools or executes anything directly.

from __future__ import annotations

from typing import Any


_CATEGORIES = {
    "browser": {
        "label": "Browser",
        "description": "Open websites and control browser",
        "tools": ["open website", "open browser", "search web"],
        "risk": "safe",
        "suggestion": "open youtube",
    },
    "apps": {
        "label": "Apps",
        "description": "Open system applications",
        "tools": ["open app", "close app", "list apps"],
        "risk": "safe",
        "suggestion": "open chrome",
    },
    "files": {
        "label": "Files",
        "description": "Create, read, and manage files",
        "tools": ["create file", "open file", "rename file", "delete file"],
        "risk": "confirm",
        "suggestion": "create folder on desktop",
    },
    "screen": {
        "label": "Screen",
        "description": "Capture and analyze screen",
        "tools": ["take screenshot", "analyze screen"],
        "risk": "confirm",
        "suggestion": "take screenshot",
    },
    "system": {
        "label": "System",
        "description": "System info and control",
        "tools": ["system info", "volume up", "volume down", "brightness"],
        "risk": "safe",
        "suggestion": "system info",
    },
    "memory": {
        "label": "Memory",
        "description": "Remember facts and preferences",
        "tools": ["remember this", "what do you know", "forget"],
        "risk": "safe",
        "suggestion": "remember this",
    },
    "search": {
        "label": "Search",
        "description": "Search the web for information",
        "tools": ["search", "find information"],
        "risk": "safe",
        "suggestion": "search latest AI news",
    },
    "developer": {
        "label": "Developer",
        "description": "Code and dev tools",
        "tools": ["create file", "read file"],
        "risk": "confirm",
        "suggestion": "read this file",
    },
}


def get_tool_categories() -> dict[str, Any]:
    categories: dict[str, Any] = {}
    try:
        from engine.tool_registry import get_registered_tools
        registered = get_registered_tools()
        registered_names = {t.get("name", "").lower() for t in registered}
    except Exception:
        registered_names = set()

    for key, cat in _CATEGORIES.items():
        safe_tools = [t for t in cat["tools"] if t.lower() in registered_names or True]
        categories[key] = {
            "label": cat["label"],
            "description": cat["description"],
            "tools": safe_tools if registered_names else cat["tools"],
            "risk": cat["risk"],
            "suggestion": cat["suggestion"],
        }
    return categories


def get_command_suggestions() -> list[dict[str, str]]:
    return [
        {"label": "Open Chrome", "text": "open chrome", "category": "apps"},
        {"label": "Open YouTube", "text": "open youtube", "category": "browser"},
        {"label": "Search AI news", "text": "search latest AI news", "category": "search"},
        {"label": "What do you know?", "text": "what did you understand?", "category": "memory"},
        {"label": "Diagnose yourself", "text": "diagnose yourself", "category": "system"},
        {"label": "Create folder", "text": "create folder on desktop", "category": "files"},
        {"label": "Remember this", "text": "remember this", "category": "memory"},
        {"label": "Copy it", "text": "copy it", "category": "system"},
    ]