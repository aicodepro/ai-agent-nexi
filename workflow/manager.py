"""Workflow manager — multi-turn dialog state machine."""

import time
import threading

_CANCEL_WORDS = {"cancel", "stop", "never mind", "nevermind", "exit",
                 "leave it", "quit", "forget it"}

_lock = threading.Lock()
_active_workflow = None  # {name, step, data, expires_at}


def is_cancel_command(text: str) -> bool:
    return text.strip().lower() in _CANCEL_WORDS


def start_workflow(name: str, data: dict = None, ttl: int = 120) -> None:
    global _active_workflow
    with _lock:
        _active_workflow = {
            "name": name, "step": "start", "data": data or {},
            "expires_at": time.time() + ttl,
        }
    print(f"[WORKFLOW] started name={name}", flush=True)


def get_active_workflow() -> dict | None:
    with _lock:
        if _active_workflow is None:
            return None
        if time.time() > _active_workflow.get("expires_at", 0):
            clear_workflow()
            return None
        return _active_workflow.copy()


def update_workflow(step: str = "", data: dict = None) -> None:
    global _active_workflow
    with _lock:
        if _active_workflow:
            if step:
                _active_workflow["step"] = step
            if data:
                _active_workflow["data"].update(data)


def clear_workflow() -> None:
    global _active_workflow
    with _lock:
        _active_workflow = None


def handle_active_workflow(query: str) -> str | None:
    """Handle user reply within an active workflow. Returns response or None."""
    wf = get_active_workflow()
    if not wf:
        return None

    if is_cancel_command(query):
        clear_workflow()
        return "Workflow cancelled."

    name = wf.get("name", "")
    step = wf.get("step", "")
    data = wf.get("data", {})

    # File creation workflow
    if name == "create_file":
        return _continue_create_file(query, step, data)

    # Project creation workflow
    if name == "create_project":
        return _continue_create_project(query, step, data)

    # Rock-paper-scissors
    if name == "rps":
        from skills.games import play_rps
        clear_workflow()
        return play_rps(query)

    clear_workflow()
    return None


def _continue_create_file(query: str, step: str, data: dict) -> str:
    from skills.files import create_file, resolve_location

    if step == "ask_name":
        name = query.strip()
        if not name:
            return "Please provide a file name."
        update_workflow(step="ask_location", data={"filename": name})
        return f"Where should I create '{name}'? (desktop, documents, or a path)"

    if step == "ask_location":
        location = query.strip() or "desktop"
        filename = data.get("filename", "untitled.txt")
        clear_workflow()
        result = create_file(filename, location)
        return result.get("message", "Done.")

    clear_workflow()
    return None


def _continue_create_project(query: str, step: str, data: dict) -> str:
    from skills.files import create_project

    if step == "ask_name":
        name = query.strip()
        if not name:
            return "Please provide a project name."
        update_workflow(step="ask_files", data={"project_name": name})
        return f"What files should I create in '{name}'? (e.g., main.py, index.html, or 'default')"

    if step == "ask_files":
        files_input = query.strip().lower()
        name = data.get("project_name", "project")
        if files_input in {"default", "yes", "ok"}:
            file_list = ["main.py"]
        else:
            file_list = [f.strip() for f in files_input.split(",") if f.strip()]
        clear_workflow()
        result = create_project(name, files=file_list)
        return result.get("message", "Done.")

    clear_workflow()
    return None
