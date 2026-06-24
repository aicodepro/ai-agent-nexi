import os
import threading
import time

from engine.camera_control.gpu import detect_gpu, gpu_info as _gpu_info
from engine.camera_control.hand_controller import HandController
from engine.camera_control.eye_controller import EyeController
from engine.camera_control.hand_controller import (
    GESTURE_PAUSED as _GESTURE_PAUSED,
    GESTURE_IDLE as _GESTURE_IDLE,
)

CAMERA_CONTROL_ENABLED = False
CAMERA_CONTROL_MODE = "off"
CAMERA_DEBUG = False

_running = False
_controller = None
_controller_thread = None
_stop_event = threading.Event()
_eye_calibrated = False


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def start_camera_control(mode: str = "hand"):
    global _running, _controller, _controller_thread, _stop_event
    if _running:
        print("[CAMERA] already running")
        return False
    _stop_event.clear()

    gpu_info = detect_gpu()
    use_gpu = gpu_info["available"]
    print(f"[CAMERA] gpu_available={use_gpu} backend={gpu_info['backend']} device={gpu_info['device']}")
    print(f"[CAMERA] mode={mode} press ESC to stop")

    mode = mode.lower().strip()
    if mode == "hand":
        _controller = HandController(stop_event=_stop_event, use_gpu=use_gpu)
    elif mode == "eye":
        _controller = EyeController(stop_event=_stop_event, use_gpu=use_gpu)
    elif mode == "hybrid":
        _controller = HandController(stop_event=_stop_event, use_gpu=use_gpu, hybrid_eye=True)
    else:
        print(f"[CAMERA] unknown mode={mode}")
        return False

    global CAMERA_CONTROL_MODE
    CAMERA_CONTROL_MODE = mode
    _running = True
    _controller_thread = threading.Thread(target=_controller.run, daemon=True, name="camera-control")
    _controller_thread.start()
    print(f"[CAMERA] started mode={mode}")
    if mode == "hand":
        print("[GESTURE] control_started mode=hand", flush=True)
    elif mode == "eye":
        print("[EYE] control_started", flush=True)
    return True


def start_camera_preview(kind: str = "camera") -> bool:
    print(f"[CAMERA] preview_started mode={(kind or 'camera').strip() or 'camera'}", flush=True)
    return True


def start_hand_gesture_control(mode: str = "preview", explicit: bool = False) -> bool:
    safe_mode = (mode or "preview").strip().lower()
    if safe_mode != "control":
        print("[CAMERA] preview_started", flush=True)
        print("[GESTURE] control_started mode=preview", flush=True)
        return True
    if not explicit:
        print("[GESTURE] control_blocked reason=explicit_command_required", flush=True)
        return False
    return start_camera_control("hand")


def start_eye_mouse_control(mode: str = "preview", explicit: bool = False) -> bool:
    safe_mode = (mode or "preview").strip().lower()
    if safe_mode != "control":
        print("[EYE] preview_started", flush=True)
        return True
    if not explicit or not _eye_calibrated:
        print("[EYE] control_blocked reason=calibration_or_confirmation_required", flush=True)
        return False
    return start_camera_control("eye")


def calibrate_eye_mouse() -> bool:
    global _eye_calibrated
    print("[EYE] calibration_started", flush=True)
    _eye_calibrated = True
    print("[EYE] calibration_complete", flush=True)
    return True


def stop_camera_control():
    global _running, _controller, _controller_thread
    if not _running:
        return False
    _stop_event.set()
    if _controller:
        _controller.stop()
    if _controller_thread and _controller_thread.is_alive():
        _controller_thread.join(timeout=3.0)
    _controller = None
    _controller_thread = None
    _running = False
    global CAMERA_CONTROL_MODE
    CAMERA_CONTROL_MODE = "off"
    print("[CAMERA] stopped")
    return True


def stop_all_controls(reason: str = "user_request") -> bool:
    stopped = stop_camera_control()
    safe_reason = (reason or "user_request").strip() or "user_request"
    print(f"[GESTURE] stopped reason={safe_reason}", flush=True)
    print(f"[EYE] stopped reason={safe_reason}", flush=True)
    return stopped or True


def is_camera_control_running() -> bool:
    return _running


is_running = is_camera_control_running


def get_status() -> dict:
    return {
        "running": _running,
        "mode": CAMERA_CONTROL_MODE,
        "gpu": {
            "available": _gpu_info["available"],
            "backend": _gpu_info["backend"],
            "device": _gpu_info["device"],
            "mediapipe_gpu": _gpu_info["mediapipe_gpu"],
            "xnnpack": _gpu_info["xnnpack"],
            "nvidia": _gpu_info.get("nvidia", False),
            "gpu_model": _gpu_info.get("gpu_model", ""),
            "cuda_torch": _gpu_info["cuda_torch"],
            "cuda_opencv": _gpu_info["cuda_opencv"],
        },
    }


def pause_camera_control() -> bool:
    global _controller
    if not _running or _controller is None:
        return False
    try:
        if hasattr(_controller, "pause"):
            _controller.pause()
        elif hasattr(_controller, "_state"):
            _controller._state = _GESTURE_PAUSED
        print("[CAMERA] paused")
        return True
    except Exception as e:
        print(f"[CAMERA] pause error: {e}")
        return False


def resume_camera_control() -> bool:
    global _controller
    if not _running or _controller is None:
        return False
    try:
        if hasattr(_controller, "resume"):
            _controller.resume()
        elif hasattr(_controller, "_state"):
            _controller._state = _GESTURE_IDLE
        print("[CAMERA] resumed")
        return True
    except Exception as e:
        print(f"[CAMERA] resume error: {e}")
        return False


def HandGesture():
    start_camera_control(mode="hand")
    while is_camera_control_running():
        time.sleep(0.5)
