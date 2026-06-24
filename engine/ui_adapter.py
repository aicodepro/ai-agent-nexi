# ui_adapter.py
#
# Single safe backend entry point for the Mark-style UI.
# All UI commands route through Jarvis command_bus.
# Never calls tools, brain, or ASR directly.

from __future__ import annotations

import os
import re
from typing import Any

_MAX_INPUT_CHARS = 4000


def submit_text(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    print(f"[UI_ADAPTER] submit_text source=mark_ui chars={len(cleaned)}", flush=True)
    if not cleaned:
        return {"ok": False, "error": "empty_input", "detail": "No text provided."}
    if len(cleaned) > _MAX_INPUT_CHARS:
        cleaned = cleaned[:_MAX_INPUT_CHARS]
        print(f"[UI_ADAPTER] text_trimmed to={_MAX_INPUT_CHARS}", flush=True)
    try:
        from engine.command_bus import submit_user_command
        ok = submit_user_command(cleaned, source="ui", mode="typed")
        return {"ok": ok, "text": cleaned[:200]}
    except Exception as e:
        print(f"[UI_ADAPTER] submit_text_failed reason={type(e).__name__}", flush=True)
        return {"ok": False, "error": "dispatch_failed", "detail": str(e)[:200]}


def submit_voice_text(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    print(f"[UI_ADAPTER] submit_voice_text chars={len(cleaned)}", flush=True)
    if not cleaned:
        return {"ok": False, "error": "empty_input"}
    if len(cleaned) > _MAX_INPUT_CHARS:
        cleaned = cleaned[:_MAX_INPUT_CHARS]
    try:
        from engine.command_bus import submit_user_command
        ok = submit_user_command(cleaned, source="ui_button", mode="voice")
        return {"ok": ok, "text": cleaned[:200]}
    except Exception as e:
        return {"ok": False, "error": "dispatch_failed", "detail": str(e)[:200]}


def submit_file_drop(file_paths: list[str]) -> dict[str, Any]:
    paths = [p.strip() for p in (file_paths or []) if p and p.strip()]
    print(f"[UI_ADAPTER] file_drop count={len(paths)}", flush=True)
    if not paths:
        return {"ok": False, "error": "no_files", "detail": "No files dropped."}
    result = {"ok": True, "files": [], "prompt": "What should I do with this file?"}
    for p in paths[:5]:
        try:
            name = os.path.basename(p)
            size = os.path.getsize(p)
            result["files"].append({"name": name, "size": size, "path": p})
        except OSError:
            result["files"].append({"name": os.path.basename(p), "error": "not_accessible"})
    return result


def get_env_status() -> dict[str, bool]:
    return {
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "gemini": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
    }


def get_runtime_status() -> dict[str, Any]:
    status: dict[str, Any] = {"mode": "mark", "providers": get_env_status()}
    try:
        from engine.jarvis_wake_controller import is_wake_enabled as _wake
        status["wake_enabled"] = _wake() if callable(_wake) else True
    except Exception:
        status["wake_enabled"] = True
    try:
        from engine.workflow_state import has_active_workflow
        status["active_workflow"] = has_active_workflow()
    except Exception:
        status["active_workflow"] = False
    return status


def get_ui_capabilities() -> dict[str, bool]:
    return {
        "file_drop": True,
        "hud_orb": True,
        "debug_log": True,
        "settings_overlay": True,
        "command_suggestions": True,
        "action_categories": True,
    }