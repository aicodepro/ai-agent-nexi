"""UI adapter — entry point for Eel-exposed functions."""

import os
from pathlib import Path
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


def submit_file_drop(paths) -> dict:
    if not paths:
        return {"status": "empty", "files": []}
    files = []
    for p in list(paths)[:5]:
        p = str(p)
        files.append({"name": os.path.basename(p) or p, "path": p})
    return {"status": "ok", "files": files}


def get_last_response() -> dict:
    from memory.context import get_last_assistant_response
    return {"text": get_last_assistant_response() or ""}


def output_action(action: str) -> dict:
    from memory.context import get_last_assistant_response, add_assistant_turn, get_recent_turns
    text = get_last_assistant_response()
    if not text:
        return {"ok": False, "message": "Nothing to act on."}

    if action == "copy":
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"ok": True, "message": "Copied to clipboard."}
        except Exception:
            return {"ok": False, "message": "Couldn't copy."}

    if action in ("save_md", "save_txt"):
        ext = "md" if action == "save_md" else "txt"
        try:
            from datetime import datetime
            desktop = Path.home() / "Desktop"
            desktop.mkdir(parents=True, exist_ok=True)
            fname = desktop / f"nexi_output_{datetime.now():%Y%m%d_%H%M%S}.{ext}"
            fname.write_text(text, encoding="utf-8")
            return {"ok": True, "message": f"Saved to {fname.name}"}
        except Exception as e:
            return {"ok": False, "message": f"Save failed: {type(e).__name__}"}

    if action == "read":
        try:
            from core.tts import speak
            speak(text)
            return {"ok": True, "message": "Reading aloud."}
        except Exception:
            return {"ok": False, "message": "Couldn't read."}

    if action in ("shorten", "regenerate"):
        try:
            from brain.gemini import ask_brain
            if action == "shorten":
                new = ask_brain("Rewrite this more concisely, keeping the key points:\n\n" + text)
            else:
                last_user = ""
                for t in reversed(get_recent_turns(10)):
                    if t.get("role") == "user":
                        last_user = t.get("text", "")
                        break
                new = ask_brain(last_user) if last_user else ask_brain("Rephrase:\n\n" + text)
            if new:
                add_assistant_turn(new, source="output_action")
                return {"ok": True, "message": action.capitalize() + "d.", "text": new}
            return {"ok": False, "message": "No response."}
        except Exception as e:
            return {"ok": False, "message": f"Failed: {type(e).__name__}"}

    return {"ok": False, "message": "Unknown action."}


def get_metrics() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        net = psutil.net_io_counters()
        return {"cpu": round(cpu), "mem": round(mem),
                "net_bytes": net.bytes_sent + net.bytes_recv}
    except Exception:
        return {}


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
