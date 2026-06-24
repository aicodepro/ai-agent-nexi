"""Desktop control — app launch, window management, process control."""

import os
import subprocess


KNOWN_APPS = {
    "chrome": "chrome.exe", "notepad": "notepad.exe",
    "calculator": "calc.exe", "vs code": "Code.exe",
    "explorer": "explorer.exe", "task manager": "Taskmgr.exe",
    "paint": "mspaint.exe", "cmd": "cmd.exe",
    "terminal": "wt.exe", "spotify": "Spotify.exe",
}


def handle_open_app(entity: str) -> dict:
    lower = entity.lower().strip()
    exe = KNOWN_APPS.get(lower)
    if exe:
        try:
            subprocess.Popen(exe, shell=False)
            return {"ok": True, "message": f"Opening {entity}."}
        except Exception as e:
            return {"ok": False, "message": f"Failed: {e}"}
    try:
        subprocess.Popen(["cmd", "/c", "start", "", entity], shell=False)
        return {"ok": True, "message": f"Opening {entity}."}
    except Exception:
        return {"ok": False, "message": f"Don't know how to open {entity}."}


def handle_close_app(entity: str) -> dict:
    lower = entity.lower().strip()
    exe = KNOWN_APPS.get(lower, f"{lower}.exe")
    try:
        subprocess.run(["taskkill", "/f", "/im", exe], capture_output=True, timeout=10)
        return {"ok": True, "message": f"Closed {entity}."}
    except Exception:
        return {"ok": False, "message": f"Couldn't close {entity}."}


def handle_list_apps(entity: str = "") -> dict:
    try:
        import psutil
        procs = set()
        for p in psutil.process_iter(["name"]):
            name = p.info.get("name", "")
            if name:
                procs.add(name)
        return {"ok": True, "message": f"Running: {', '.join(sorted(procs)[:20])}"}
    except ImportError:
        return {"ok": False, "message": "psutil not installed."}


def register_desktop_controls(registry):
    registry.register("open_app", handle_open_app, risk="safe", description="Open an application")
    registry.register("close_app", handle_close_app, risk="medium", description="Close an application")
    registry.register("list_apps", handle_list_apps, risk="safe", description="List running apps")
