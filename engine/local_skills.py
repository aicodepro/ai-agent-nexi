from __future__ import annotations

import os
import re
import subprocess
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from engine.workflow_state import start_workflow, get_workflow, update_workflow, clear_workflow


@dataclass
class SkillResult:
    handled: bool
    message: str = ""


APP_COMMANDS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
}

SITES = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
}

FILE_TYPES = {
    "text": ".txt",
    "txt": ".txt",
    "python": ".py",
    "py": ".py",
    "html": ".html",
    "react": ".jsx",
}

YES = {"yes", "yeah", "yep", "sure", "ok", "okay", "do it", "confirm"}
NO = {"no", "nope", "nah", "don't", "dont"}
INVALID_CHARS = set('<>:"/\\|?*')


def _norm(text: str) -> str:
    return (text or "").strip().lower().rstrip(".!?").strip()


def _strip_prefix(text: str, prefixes) -> str:
    q = (text or "").strip()
    low = q.lower()
    for prefix in prefixes:
        if low == prefix:
            return ""
        if low.startswith(prefix + " "):
            return q[len(prefix):].strip()
    return ""


def _yes_no(text: str):
    q = _norm(text)
    if q in YES:
        return True
    if q in NO:
        return False
    return None


def _safe_name(name: str) -> str | None:
    n = (name or "").strip().strip('"')
    if not n or n in {".", ".."} or ".." in n:
        return None
    if any(ch in INVALID_CHARS for ch in n):
        return None
    return n[:160]


def resolve_location(text: str) -> Path | None:
    q = _norm(text)
    home = Path.home()
    aliases = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "pictures": home / "Pictures",
        "current folder": Path.cwd(),
        "current directory": Path.cwd(),
        "e drive": Path("E:/"),
        "e": Path("E:/"),
    }
    for key, path in aliases.items():
        if q == key or key in q:
            return path
    return None


def _location_label(path: Path) -> str:
    try:
        home = Path.home()
        for label in ("Desktop", "Documents", "Downloads", "Pictures"):
            if path == home / label:
                return label
    except Exception:
        pass
    return str(path)


def _starter_content(file_type: str) -> str:
    ft = _norm(file_type)
    if ft == "python" or ft == "py":
        return 'print("Hello from Nexi")\n'
    if ft == "html":
        return "<!doctype html>\n<html>\n<body>\n  <h1>Hello from Nexi</h1>\n</body>\n</html>\n"
    if ft == "react":
        return "export default function App() {\n  return <h1>Hello from Nexi</h1>;\n}\n"
    return ""


def _open_app(app_name: str) -> str:
    app = _norm(app_name)
    command = APP_COMMANDS.get(app)
    if command:
        try:
            subprocess.Popen(command, shell=True)
        except Exception:
            pass
        return f"Opening {app_name}."
    try:
        import pyautogui
        pyautogui.press("win")
        pyautogui.write(app_name)
        pyautogui.press("enter")
    except Exception:
        pass
    return f"Opening {app_name}."


def _open_website(site: str) -> str:
    raw = (site or "").strip()
    q = _norm(raw)
    url = SITES.get(q, raw)
    if not re.match(r"^https?://", url):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opening {raw}."


def _web_search(query: str) -> str:
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query.strip()))
    return f"Searching the web for {query.strip()}."


def open_app(app_name: str) -> dict:
    message = _open_app(app_name)
    return {"success": True, "message": message, "tool": "open_app", "verified": True}


def open_website(url: str = "", site: str = "") -> dict:
    target = url or site
    message = _open_website(target)
    return {"success": True, "message": message, "tool": "open_website", "verified": True}


def web_search(query: str) -> dict:
    message = _web_search(query)
    return {"success": True, "message": message, "tool": "web_search", "verified": True}


def _take_screenshot() -> str:
    folder = Path.home() / "Pictures" / "Nexi Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"nexi-screenshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    import pyautogui
    pyautogui.screenshot().save(str(target))
    return f"Screenshot saved to {target}."


def _save_note(text: str) -> str:
    folder = Path.home() / "Documents" / "Nexi Notes"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{datetime.now().strftime('%Y-%m-%d')}-notes.txt"
    with target.open("a", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    try:
        from engine.memory_store import add_note
        add_note(text)
    except Exception:
        pass
    return "Note saved."


def _create_file(slots: dict) -> str:
    name = _safe_name(slots.get("file_name", ""))
    location = slots.get("location_path")
    file_type = _norm(slots.get("file_type", "text"))
    if not name or not location:
        clear_workflow()
        return "Cancelled."
    ext = FILE_TYPES.get(file_type, ".txt")
    if not Path(name).suffix:
        name += ext
    base = Path(location).resolve()
    target = (base / name).resolve()
    try:
        if os.path.commonpath([str(base), str(target)]) != str(base):
            return "I can't create a file there."
    except ValueError:
        return "I can't create a file there."
    if target.exists():
        return "That file already exists."
    base.mkdir(parents=True, exist_ok=True)
    content = _starter_content(file_type) if slots.get("starter") else ""
    target.write_text(content, encoding="utf-8")
    return "Done. File created."


def _create_project(slots: dict) -> str:
    name = _safe_name(slots.get("folder_name", ""))
    location = slots.get("location_path")
    if not name or not location:
        clear_workflow()
        return "Cancelled."
    base = Path(location).resolve()
    target = (base / name).resolve()
    try:
        if os.path.commonpath([str(base), str(target)]) != str(base):
            return "I can't create a folder there."
    except ValueError:
        return "I can't create a folder there."
    if target.exists():
        return "That folder already exists."
    target.mkdir(parents=True)
    if slots.get("starter"):
        kind = _norm(slots.get("starter_type", "text"))
        if kind == "html":
            (target / "index.html").write_text(_starter_content("html"), encoding="utf-8")
        elif kind == "python":
            (target / "main.py").write_text(_starter_content("python"), encoding="utf-8")
        elif kind == "react":
            (target / "App.jsx").write_text(_starter_content("react"), encoding="utf-8")
        else:
            (target / "README.txt").write_text("Created by Nexi.\n", encoding="utf-8")
    if slots.get("open_vscode"):
        try:
            subprocess.Popen(f'code "{target}"', shell=True)
        except Exception:
            pass
    return "Done. Project folder created."


def handle_local_skill(query: str) -> SkillResult:
    q = _norm(query)
    if not q:
        return SkillResult(False)

    if q in {"open app", "open an app", "open application"}:
        start_workflow("local_open_app", "ask_app", {})
        return SkillResult(True, "Which app should I open?")
    app = _strip_prefix(query, ["open", "launch", "start"])
    if app and _norm(app) in APP_COMMANDS:
        return SkillResult(True, _open_app(app))

    if q in {"open website", "open a website"}:
        start_workflow("local_open_website", "ask_site", {})
        return SkillResult(True, "Which website should I open?")
    site = _strip_prefix(query, ["open website", "open site", "go to", "navigate to", "take me to"])
    if site:
        return SkillResult(True, _open_website(site))
    if app and (_norm(app) in SITES or "." in app):
        return SkillResult(True, _open_website(app))

    search = _strip_prefix(query, ["search web", "search the web", "google", "search"])
    if q in {"search web", "search the web", "google", "search"}:
        start_workflow("local_web_search", "ask_query", {})
        return SkillResult(True, "What should I search for?")
    if search:
        return SkillResult(True, _web_search(search))

    if q in {"take screenshot", "capture screen", "screenshot"}:
        return SkillResult(True, _take_screenshot())

    note = _strip_prefix(query, ["take note", "write note", "save note"])
    if q in {"take note", "write note", "save note"}:
        start_workflow("local_note", "ask_text", {})
        return SkillResult(True, "What should I write in the note?")
    if note:
        return SkillResult(True, _save_note(note))

    if q in {"create project folder", "create a project folder", "new project folder"}:
        start_workflow("local_project_folder", "ask_name", {})
        return SkillResult(True, "What should I name the folder?")

    if q.startswith("create file") or q.startswith("create a file") or q.startswith("create text file") or q.startswith("create python file"):
        slots = {}
        if "python" in q:
            slots["file_type"] = "python"
        elif "text" in q:
            slots["file_type"] = "text"
        start_workflow("local_create_file", "ask_name", slots)
        return SkillResult(True, "What should I name the file?")

    if app:
        return SkillResult(True, _open_app(app))
    return SkillResult(False)


def continue_workflow(reply: str) -> str:
    wf = get_workflow()
    if not wf:
        return "Cancelled."
    name = wf.get("name")
    slots = dict(wf.get("slots", {}))
    step = wf.get("step")

    if name == "local_open_app":
        clear_workflow()
        return _open_app(reply)
    if name == "local_open_website":
        clear_workflow()
        return _open_website(reply)
    if name == "local_web_search":
        clear_workflow()
        return _web_search(reply)
    if name == "local_note":
        clear_workflow()
        return _save_note(reply)
    if name == "local_create_file":
        return _continue_create_file(reply, step, slots)
    if name == "local_project_folder":
        return _continue_project_folder(reply, step, slots)
    clear_workflow()
    return "Cancelled."


def _continue_create_file(reply: str, step: str, slots: dict) -> str:
    if step == "ask_name":
        name = _safe_name(reply)
        if not name:
            return "What should I name the file?"
        slots["file_name"] = name
        update_workflow("ask_location", slots)
        return "Where should I create it?"
    if step == "ask_location":
        location = resolve_location(reply)
        if not location:
            return "I can use Desktop, Documents, Downloads, Pictures, E drive, or current folder. Where should I create it?"
        slots["location_path"] = str(location)
        slots["location_label"] = _location_label(location)
        if not slots.get("file_type"):
            update_workflow("ask_type", slots)
            return "What type? Text, Python, HTML, or React?"
        update_workflow("ask_starter", slots)
        return "Should I add starter content?"
    if step == "ask_type":
        ft = _norm(reply)
        if ft not in FILE_TYPES:
            return "What type? Text, Python, HTML, or React?"
        slots["file_type"] = "python" if ft == "py" else ("text" if ft == "txt" else ft)
        update_workflow("ask_starter", slots)
        return "Should I add starter content?"
    if step == "ask_starter":
        answer = _yes_no(reply)
        if answer is None:
            return "Please say yes or no. Should I add starter content?"
        slots["starter"] = answer
        update_workflow("confirm", slots)
        return f"Create {slots['file_name']} in {slots['location_label']}?"
    if step == "confirm":
        answer = _yes_no(reply)
        if answer is None:
            return f"Please say yes or no. Create {slots.get('file_name', 'the file')}?"
        if not answer:
            clear_workflow()
            return "Cancelled."
        msg = _create_file(slots)
        clear_workflow()
        return msg
    clear_workflow()
    return "Cancelled."


def _continue_project_folder(reply: str, step: str, slots: dict) -> str:
    if step == "ask_name":
        name = _safe_name(reply)
        if not name:
            return "What should I name the folder?"
        slots["folder_name"] = name
        update_workflow("ask_location", slots)
        return "Where should I create it?"
    if step == "ask_location":
        location = resolve_location(reply)
        if not location:
            return "I can use Desktop, Documents, Downloads, Pictures, E drive, or current folder. Where should I create it?"
        slots["location_path"] = str(location)
        slots["location_label"] = _location_label(location)
        update_workflow("ask_starter", slots)
        return "Should I add starter files?"
    if step == "ask_starter":
        answer = _yes_no(reply)
        if answer is None:
            return "Please say yes or no. Should I add starter files?"
        slots["starter"] = answer
        update_workflow("ask_type" if answer else "ask_vscode", slots)
        return "What type? HTML, Python, React, or text?" if answer else "Should I open it in VS Code?"
    if step == "ask_type":
        ft = _norm(reply)
        if ft not in {"html", "python", "react", "text"}:
            return "What type? HTML, Python, React, or text?"
        slots["starter_type"] = ft
        update_workflow("ask_vscode", slots)
        return "Should I open it in VS Code?"
    if step == "ask_vscode":
        answer = _yes_no(reply)
        if answer is None:
            return "Please say yes or no. Should I open it in VS Code?"
        slots["open_vscode"] = answer
        update_workflow("confirm", slots)
        return f"Create project {slots['folder_name']} in {slots['location_label']}?"
    if step == "confirm":
        answer = _yes_no(reply)
        if answer is None:
            return f"Please say yes or no. Create project {slots.get('folder_name', 'the folder')}?"
        if not answer:
            clear_workflow()
            return "Cancelled."
        msg = _create_project(slots)
        clear_workflow()
        return msg
    clear_workflow()
    return "Cancelled."
