from __future__ import annotations

import re


LONG_THRESHOLD = 700


def _summary(text: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:limit].rstrip() + ("..." if len(value) > limit else "")


def _type_for(text: str, content_type: str, user_intent: str) -> str:
    ctype = (content_type or "text").lower()
    if ctype != "text":
        return ctype
    lower = f"{user_intent}\n{text}".lower()
    if "```" in text or re.search(r"\b(def|class|function|const|import)\b", text):
        return "code"
    if any(word in lower for word in ("essay", "article")):
        return "essay"
    if any(word in lower for word in ("report", "analysis")):
        return "report"
    if any(word in lower for word in ("recipe", "steps", "list")):
        return "note"
    return "text"


def route_assistant_output(display_text: str, spoken_text: str = "", content_type: str = "text", user_intent: str = "") -> dict:
    text = str(display_text or "")
    intent = str(user_intent or "").lower()
    ctype = _type_for(text, content_type, intent)
    line_count = len([line for line in text.splitlines() if line.strip()])
    list_heavy = len(re.findall(r"(^|\n)\s*(?:[-*]|\d+[.)])\s+", text)) >= 4
    explicit_here = "show here" in intent or "main ui" in intent
    force_workspace = any(word in intent for word in ("copy", "save", "create file", "workspace", "box"))
    show_workspace = not explicit_here and (force_workspace or len(text) > LONG_THRESHOLD or ctype in {"code", "essay", "report", "search"} or line_count >= 12 or list_heavy)
    if show_workspace:
        print(f"[OUTPUT] route=workspace reason={'long' if len(text) > LONG_THRESHOLD else 'structured'}", flush=True)
        print(f"[OUTPUT] route=workspace type={ctype}", flush=True)
        spoken = spoken_text or "Here's the short version. I've put the full answer on screen."
        return {
            "main_ui_text": "I've prepared it in the workspace.",
            "show_workspace": True,
            "workspace_title": "Jarvis Output",
            "workspace_type": ctype,
            "workspace_summary": _summary(text),
            "workspace_content": text,
            "spoken_text": spoken,
            "actions": ["copy", "create_file", "save_md", "save_txt", "read_summary"],
        }
    print("[OUTPUT] route=main reason=short", flush=True)
    return {
        "main_ui_text": text,
        "show_workspace": False,
        "workspace_title": "",
        "workspace_type": ctype,
        "workspace_summary": "",
        "workspace_content": "",
        "spoken_text": spoken_text or text,
        "actions": [],
    }
