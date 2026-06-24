import subprocess
import os

from src.orin.control.base import ControlResult


KNOWN_APPS = {
    "chrome": {"exe": "chrome", "path": None},
    "notepad": {"exe": "notepad", "path": "notepad.exe"},
    "vscode": {"exe": "code", "path": "code"},
    "code": {"exe": "code", "path": "code"},
    "visual studio code": {"exe": "code", "path": "code"},
    "file explorer": {"exe": "explorer", "path": "explorer"},
    "explorer": {"exe": "explorer", "path": "explorer"},
    "cmd": {"exe": "cmd", "path": "cmd"},
    "command prompt": {"exe": "cmd", "path": "cmd"},
    "paint": {"exe": "paint", "path": "paint"},
    "calculator": {"exe": "calc", "path": "calc"},
    "word": {"exe": "winword", "path": "winword"},
    "excel": {"exe": "excel", "path": "excel"},
    "powerpoint": {"exe": "powerpnt", "path": "powerpnt"},
    "settings": {"exe": "SystemSettings", "path": "start ms-settings:"},
}


def start_process(app_name):
    app_name = app_name.lower().strip()
    if app_name in KNOWN_APPS:
        info = KNOWN_APPS[app_name]
        try:
            if info["path"]:
                if info["path"].startswith("start "):
                    os.system(info["path"])
                else:
                    os.system(f'start {info["path"]}')
            else:
                os.system(f'start {info["exe"]}')
            return ControlResult.success(message=f"Started {app_name.title()}")
        except Exception as e:
            return ControlResult.failure(
                message=f"Failed to start {app_name}",
                code="START_FAILED",
                error_message=str(e)
            )
    try:
        os.system(f'start {app_name}')
        return ControlResult.success(message=f"Started {app_name.title()}")
    except Exception as e:
        return ControlResult.failure(
            message=f"Failed to start {app_name}",
            code="START_FAILED",
            error_message=str(e)
        )


def kill_process(app_name):
    app_name = app_name.lower().strip()
    exe_name = KNOWN_APPS.get(app_name, {}).get("exe", app_name)
    try:
        subprocess.run(
            f"taskkill /f /im {exe_name}.exe",
            shell=True, capture_output=True, text=True, timeout=10
        )
        return ControlResult.success(message=f"Closed {app_name.title()}")
    except subprocess.TimeoutExpired:
        return ControlResult.failure(
            message=f"Timed out killing {app_name}",
            code="KILL_TIMEOUT"
        )
    except Exception as e:
        return ControlResult.failure(
            message=f"Failed to close {app_name}",
            code="KILL_FAILED",
            error_message=str(e)
        )


def list_running():
    try:
        import psutil
        processes = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pinfo = proc.info
                if pinfo["name"]:
                    processes.append({"pid": pinfo["pid"], "name": pinfo["name"]})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        unique = {}
        for p in processes:
            name = p["name"].lower()
            if name not in unique:
                unique[name] = {"name": p["name"], "pid": p["pid"]}
        return ControlResult.success(
            message=f"Found {len(unique)} running applications",
            data={"apps": list(unique.values())}
        )
    except ImportError:
        return ControlResult.failure(
            message="psutil not available",
            code="MISSING_DEPENDENCY"
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to list processes",
            code="LIST_FAILED",
            error_message=str(e)
        )
