"""Nexi — UI process entry point."""

import os
import sys
import subprocess
import eel
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.config import cfg, env_int
from ui.loader import init_eel, edge_window_args, should_open_fullscreen


# --- Eel-exposed API ---

@eel.expose
def ui_submit_text(text):
    from ui.adapter import submit_text
    return submit_text(text)


@eel.expose
def ui_submit_file_drop(paths):
    from ui.adapter import submit_file_drop
    return submit_file_drop(paths)


@eel.expose
def ui_get_metrics():
    from ui.adapter import get_metrics
    return get_metrics()


@eel.expose
def ui_get_last_response():
    from ui.adapter import get_last_response
    return get_last_response()


@eel.expose
def ui_output_action(action):
    from ui.adapter import output_action
    return output_action(action)


@eel.expose
def ui_get_env_status():
    from ui.adapter import get_env_status
    return get_env_status()


@eel.expose
def ui_get_runtime_status():
    from ui.adapter import get_runtime_status
    return get_runtime_status()


@eel.expose
def ui_get_capabilities():
    from ui.adapter import get_capabilities
    return get_capabilities()


@eel.expose
def ui_get_tool_categories():
    from ui.adapter import get_tool_categories
    return get_tool_categories()


@eel.expose
def ui_get_suggestions():
    from ui.adapter import get_suggestions
    return get_suggestions()


@eel.expose
def submitUserCommand(text):
    """DEPRECATED: Use ui_submit_text instead."""
    from core.dispatcher import submit_user_command
    submit_user_command(text, source="ui_text")


@eel.expose
def wakeNexiFromUi(source="ui_button"):
    from core.ui_state import emit_state
    emit_state("listening", source=source)


@eel.expose
def emergencyStop():
    from control.gate import engage_emergency_stop
    engage_emergency_stop()
    return {"ok": True}


@eel.expose
def clearEmergencyStop():
    from control.gate import clear_emergency_stop
    clear_emergency_stop()
    return {"ok": True}


@eel.expose
def getMemorySummary():
    try:
        from memory.manager import build_memory_context
        return {"summary": build_memory_context(limit=10)}
    except Exception:
        return {"summary": "Memory unavailable."}


# --- Startup ---

def _start_server(command_queue=None, stop_event=None, wake_ready=None, speaking_event=None):
    init_eel(eel)

    try:
        from core.tts import set_speaking_event
        set_speaking_event(speaking_event)
    except Exception as e:
        print(f"[NEXI] set_speaking_event_failed: {e}", flush=True)

    # DEPRECATED: control/ module is legacy. Skills are in skills/ package.
    try:
        from control.registry import register_defaults
        register_defaults()
    except Exception as e:
        print(f"[NEXI] control_registry_failed: {e}", flush=True)

    # Start reminder/alarm scheduler
    try:
        from skills.scheduler import start_scheduler
        start_scheduler(stop_event)
    except Exception as e:
        print(f"[NEXI] scheduler_failed: {e}", flush=True)

    # Start bridge pump
    if command_queue is not None:
        try:
            from core.bridge import start_ui_bridge_pump
            start_ui_bridge_pump(command_queue, stop_event)
        except Exception as e:
            print(f"[NEXI] bridge_pump_failed: {e}", flush=True)

    # Wait for the wake pipeline to come up before showing the window, so the
    # UI never appears before hotword detection is ready. Bounded so a failed
    # wake process can't block the UI forever.
    if wake_ready is not None:
        wait_s = env_int("UI_WAIT_FOR_WAKE_SECONDS", 20)
        print(f"[NEXI] ui waiting for wake_ready (timeout={wait_s}s)", flush=True)
        if wake_ready.wait(timeout=wait_s):
            print("[NEXI] wake_ready received, opening UI", flush=True)
        else:
            print("[NEXI] wake_ready timeout, opening UI anyway", flush=True)

    # Launch Edge in app mode
    url = "http://localhost:8000/index.html"
    try:
        args = ["cmd", "/c", "start", "", "msedge.exe", *edge_window_args(), f"--app={url}"]
        subprocess.Popen(args)
    except Exception:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "msedge.exe", "--start-maximized", f"--app={url}"])
        except Exception as e:
            print(f"[NEXI] edge_launch_failed: {e}", flush=True)

    print(f"[NEXI] eel starting on localhost:8000", flush=True)
    eel.start("index.html", mode=None, host="localhost", port=8000, block=True)


def main(command_queue=None, stop_event=None, wake_ready=None, speaking_event=None):
    print(f"[NEXI] main pid={os.getpid()}", flush=True)
    _start_server(command_queue=command_queue, stop_event=stop_event, wake_ready=wake_ready,
                  speaking_event=speaking_event)


if __name__ == "__main__":
    main()
