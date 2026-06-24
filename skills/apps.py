"""App launching and management."""

import os
import re
import subprocess

APP_MAP = {
    "chrome": "chrome", "google chrome": "chrome",
    "notepad": "notepad", "calculator": "calc",
    "vs code": "code", "vscode": "code", "visual studio code": "code",
    "file explorer": "explorer", "explorer": "explorer",
    "task manager": "taskmgr", "cmd": "cmd",
    "paint": "mspaint", "word": "winword",
    "excel": "excel", "powerpoint": "powerpnt",
    "spotify": "spotify", "discord": "discord",
    "teams": "teams", "slack": "slack",
    "terminal": "wt", "windows terminal": "wt",
}


def open_app(name: str) -> dict:
    lower = name.lower().strip()
    cmd = APP_MAP.get(lower)
    if cmd:
        try:
            subprocess.Popen(cmd, shell=False)
            return {"handled": True, "message": f"Opening {name}."}
        except Exception as e:
            return {"handled": False, "message": f"Couldn't open {name}: {e}"}

    # Try os.system as fallback
    try:
        subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
        return {"handled": True, "message": f"Opening {name}."}
    except Exception:
        return {"handled": False, "message": f"I don't know how to open {name}."}


def close_app(name: str) -> dict:
    lower = name.lower().strip()
    cmd = APP_MAP.get(lower, lower)
    try:
        subprocess.run(["taskkill", "/f", "/im", f"{cmd}.exe"], capture_output=True, timeout=10)
        return {"handled": True, "message": f"Closed {name}."}
    except Exception:
        return {"handled": False, "message": f"Couldn't close {name}."}
