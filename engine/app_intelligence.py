"""Intelligent App Resolver (Roadmap Feature #2) — map a task/intent to the right app.

Tool cards
----------
resolve_app_for_task role: app intelligence | risk: LOW    | confirm: never | verifier: app candidate + confidence returned | memory: never store
open_app_for_task    role: app intelligence | risk: MEDIUM | confirm: never | verifier: open_app reports success           | memory: never store

`resolve_app_for_task` is READ-ONLY: given a task ("coding", "presentation"), it returns the
best-fit application plus a confidence score and whether it appears installed — it never
launches or installs anything. `open_app_for_task` resolves then opens via the existing
`open_app` skill (it never installs apps). Installed-app detection is a best-effort, read-only
scan of the Start Menu; it degrades gracefully (lower confidence) when it can't read.
"""

from __future__ import annotations

import os
from typing import Any


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "app_intelligence"), "message": message, **extra}


def _fail(message: str, tool: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": False, "success": False, "verified": False,
            "tool": tool, "message": message, **extra}


# task category -> ordered (exe/alias key, friendly name) candidates, best first
_TASK_APPS: dict[str, list[tuple[str, str]]] = {
    "coding": [("code", "VS Code"), ("pycharm", "PyCharm"), ("devenv", "Visual Studio"), ("sublime_text", "Sublime Text")],
    "browsing": [("chrome", "Chrome"), ("msedge", "Edge"), ("firefox", "Firefox")],
    "presentation": [("powerpnt", "PowerPoint"), ("canva", "Canva")],
    "writing": [("winword", "Word"), ("notepad", "Notepad")],
    "spreadsheet": [("excel", "Excel")],
    "email": [("outlook", "Outlook")],
    "music": [("spotify", "Spotify")],
    "notes": [("notepad", "Notepad")],
    "terminal": [("wt", "Terminal"), ("powershell", "PowerShell"), ("cmd", "Command Prompt")],
    "calculator": [("calc", "Calculator")],
    "pdf": [("acrobat", "Adobe Acrobat"), ("msedge", "Edge")],
    "photo editing": [("photoshop", "Photoshop"), ("canva", "Canva")],
}

# free-text keyword -> canonical category (longest key wins on fuzzy contains)
_TASK_SYNONYMS: dict[str, str] = {
    "coding": "coding", "code": "coding", "programming": "coding", "program": "coding",
    "develop": "coding", "development": "coding", "dev": "coding",
    "browsing": "browsing", "browser": "browsing", "web": "browsing", "internet": "browsing", "surf": "browsing",
    "presentation": "presentation", "presentations": "presentation", "slides": "presentation",
    "slideshow": "presentation", "present": "presentation", "make slides": "presentation",
    "writing": "writing", "write": "writing", "document": "writing", "documents": "writing", "essay": "writing",
    "spreadsheet": "spreadsheet", "spreadsheets": "spreadsheet", "excel": "spreadsheet", "data": "spreadsheet",
    "email": "email", "emails": "email", "mail": "email",
    "music": "music", "song": "music", "songs": "music", "listen": "music",
    "notes": "notes", "note": "notes",
    "terminal": "terminal", "shell": "terminal", "command line": "terminal", "cli": "terminal",
    "calculator": "calculator", "calculate": "calculator", "math": "calculator",
    "pdf": "pdf", "pdfs": "pdf",
    "photo editing": "photo editing", "photo": "photo editing", "image editing": "photo editing",
}

_index_cache: set[str] | None = None


def _start_menu_dirs() -> list[str]:
    dirs = []
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if base:
            dirs.append(os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"))
    return dirs


def build_index(refresh: bool = False) -> set[str]:
    """Best-effort, read-only set of lowercased installed-app shortcut names."""
    global _index_cache
    if _index_cache is not None and not refresh:
        return _index_cache
    tokens: set[str] = set()
    try:
        for d in _start_menu_dirs():
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        tokens.add(os.path.splitext(f)[0].lower())
    except Exception:
        pass
    _index_cache = tokens
    return tokens


def _is_installed(key: str, friendly: str, index: set[str]) -> bool:
    k, fr = key.lower(), friendly.lower()
    for token in index:
        if k in token or fr in token:
            return True
    return False


def _match_category(task: str) -> str:
    t = " ".join(str(task or "").strip().lower().rstrip(".?!").split())
    if not t:
        return ""
    if t in _TASK_SYNONYMS:
        return _TASK_SYNONYMS[t]
    best_cat, best_len = "", 0
    for syn, cat in _TASK_SYNONYMS.items():
        if syn in t and len(syn) > best_len:
            best_cat, best_len = cat, len(syn)
    return best_cat


def resolve_for_task(task: str) -> dict[str, Any]:
    """Return the best app for a task with a confidence score. Pure / read-only."""
    category = _match_category(task)
    if category:
        index = build_index()
        candidates = _TASK_APPS[category]
        for key, friendly in candidates:
            if _is_installed(key, friendly, index):
                return {"task": task, "category": category, "app": friendly, "app_key": key,
                        "confidence": 0.9, "installed": True,
                        "candidates": [c[1] for c in candidates]}
        key, friendly = candidates[0]
        return {"task": task, "category": category, "app": friendly, "app_key": key,
                "confidence": 0.55, "installed": False,
                "candidates": [c[1] for c in candidates]}
    # No category — treat the task text as an app name.
    from engine.app_resolver import resolve_app_name
    resolved = resolve_app_name(task)
    name = str(resolved.get("app_name") or task).strip()
    return {"task": task, "category": "", "app": name, "app_key": name,
            "confidence": 0.4 if resolved.get("matched") else 0.3,
            "installed": bool(resolved.get("matched")), "candidates": [name]}


def resolve_app_for_task(slots: dict | None = None) -> dict[str, Any]:
    task = str((slots or {}).get("task") or (slots or {}).get("text") or "").strip()
    if not task:
        return _fail("Which task should I find an app for?", "resolve_app_for_task",
                     expects_user_reply=True, missing_slot="task")
    r = resolve_for_task(task)
    where = r["category"] or task
    tail = " (installed)" if r["installed"] else ""
    msg = f"For {where}, I'd use {r['app']}{tail}."
    return _ok(msg, tool="resolve_app_for_task", **r)


def _open_app(name: str) -> dict[str, Any]:
    """Indirection over the existing open_app skill (isolated for testability)."""
    from engine import local_skills
    return local_skills.open_app(name)


def open_app_for_task(slots: dict | None = None) -> dict[str, Any]:
    task = str((slots or {}).get("task") or (slots or {}).get("text") or "").strip()
    if not task:
        return _fail("Which task should I open an app for?", "open_app_for_task",
                     expects_user_reply=True, missing_slot="task")
    r = resolve_for_task(task)
    target = r["app_key"] or r["app"]
    result = _open_app(target)
    if result.get("success"):
        where = r["category"] or task
        return _ok(f"Opening {r['app']} for {where}.", tool="open_app_for_task", **r)
    return _fail(f"I found {r['app']} for {task}, but couldn't open it.", "open_app_for_task", **r)
