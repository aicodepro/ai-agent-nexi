"""Start/stop camera-based control as an on-demand subprocess.

The heavy vision deps (mediapipe/opencv) load only inside the subprocess, so
they never weigh down the main UI process.
"""

import subprocess
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_proc = None


def _running() -> bool:
    return _proc is not None and _proc.poll() is None


def _start(mode: str, label: str, hint: str) -> dict:
    global _proc
    if _running():
        return {"handled": True, "message": "Camera control is already running. Say 'stop camera' to end it."}
    try:
        _proc = subprocess.Popen([sys.executable, "-m", "vision.runner", mode], cwd=str(_BASE))
        return {"handled": True, "message": f"{label} started. {hint} Press Q in the window or say 'stop camera' to end."}
    except Exception as e:
        return {"handled": False, "message": f"Couldn't start camera control: {e}"}


def start_hand_control() -> dict:
    return _start("hand", "Hand control", "Move your index finger to steer, pinch to click.")


def start_eye_control() -> dict:
    return _start("eye", "Face control", "Move your head to steer, open your mouth to click.")


def stop_camera() -> dict:
    global _proc
    if _running():
        _proc.terminate()
        _proc = None
        return {"handled": True, "message": "Camera control stopped."}
    return {"handled": True, "message": "Camera control isn't running."}
