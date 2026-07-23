import os
import pyautogui
import threading
import time

from engine.camera_control.gpu import get_gpu_info
from engine.camera_control.hand_controller import HandController
from engine.camera_control.eye_controller import EyeController
from engine.camera_control.hand_controller import (
    GESTURE_PAUSED as _GESTURE_PAUSED,
    GESTURE_IDLE as _GESTURE_IDLE,
)


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


CAMERA_CONTROL_ENABLED = _env_bool("CAMERA_CONTROL_ENABLED", True)
CAMERA_CONTROL_MODE = (os.getenv("CAMERA_CONTROL_MODE", "off") or "off").strip().lower()
CAMERA_ON_STARTUP = _env_bool("CAMERA_ON_STARTUP", False)
CAMERA_DEBUG = _env_bool("CAMERA_DEBUG", False)

_running = False
_controller = None
_controller_thread = None
_stop_event = threading.Event()
_eye_calibrated = False
_last_status = {"ok": True, "status": "stopped", "reason": ""}

# Face recognition state
_face_recognizer_instance = None
_face_recognition_thread = None
_face_authenticated = False
_face_names = {}


def start_camera_control(mode: str = "hand"):
    global _running, _controller, _controller_thread, _stop_event, _last_status
    if _running:
        print("[CAMERA] already running")
        return False
    _stop_event.clear()

    gpu_info = get_gpu_info()
    use_gpu = gpu_info["mediapipe_gpu"]
    if not use_gpu and gpu_info["available"]:
        print(f"[CAMERA] torch_cuda={gpu_info['cuda_torch']} but mediapipe_gpu=False — forcing CPU delegate")
    print(f"[CAMERA] mediapipe_gpu={use_gpu} backend={gpu_info['backend']} device={gpu_info['device']}")
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
    _last_status = {"ok": True, "status": "running", "reason": ""}
    _controller_thread = threading.Thread(
        target=_run_camera_controller, args=(_controller,), daemon=True, name="camera-control"
    )
    _controller_thread.start()
    print(f"[CAMERA] started mode={mode}")
    if mode == "hand":
        print("[GESTURE] control_started mode=hand", flush=True)
    elif mode == "eye":
        print("[EYE] control_started", flush=True)
    return True


def _run_camera_controller(controller):
    global _running, _last_status
    try:
        result = controller.run()
        if isinstance(result, dict):
            _last_status = result
    except pyautogui.FailSafeException:
        _stop_event.set()
        try:
            controller.stop()
        except pyautogui.FailSafeException:
            pass
        _last_status = {"ok": False, "status": "stopped", "reason": "failsafe"}
    except Exception as e:
        _last_status = {
            "ok": False,
            "status": "unavailable",
            "reason": "controller_error",
            "detail": f"{type(e).__name__}: {e}",
        }
    finally:
        _running = False


def start_camera_preview(kind: str = "camera") -> bool:
    print(f"[CAMERA] preview_started mode={(kind or 'camera').strip() or 'camera'}", flush=True)
    return True


def start_hand_gesture_control(mode: str = "preview", explicit: bool = True) -> bool:
    safe_mode = (mode or "preview").strip().lower()
    if safe_mode != "control":
        print("[CAMERA] preview_started", flush=True)
        print("[GESTURE] control_started mode=preview", flush=True)
        return True
    if not explicit:
        print("[GESTURE] control_blocked reason=explicit_command_required", flush=True)
        return False
    return start_camera_control("hand")


def start_eye_mouse_control(mode: str = "preview", explicit: bool = True) -> bool:
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
    global _running, _controller, _controller_thread, _last_status
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
    _last_status = {"ok": True, "status": "stopped", "reason": "user_request"}
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
    gpu_info = get_gpu_info()
    return {
        "running": _running,
        "mode": CAMERA_CONTROL_MODE,
        "status": _last_status["status"],
        "reason": _last_status.get("reason", ""),
        "gpu": {
            "available": gpu_info["available"],
            "backend": gpu_info["backend"],
            "device": gpu_info["device"],
            "mediapipe_gpu": gpu_info["mediapipe_gpu"],
            "xnnpack": gpu_info["xnnpack"],
            "nvidia": gpu_info.get("nvidia", False),
            "gpu_model": gpu_info.get("gpu_model", ""),
            "cuda_torch": gpu_info["cuda_torch"],
            "cuda_opencv": gpu_info["cuda_opencv"],
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


# ── Face Recognition ────────────────────────────────────────────────────────

def start_face_recognition() -> bool:
    global _face_recognizer_instance, _face_recognition_thread, _face_authenticated, _face_names
    if _face_recognizer_instance is not None:
        print("[FACE] already running")
        return True
    try:
        from engine.camera_control.face_recognizer import FaceRecognizer
    except Exception as e:
        print(f"[FACE] import_error reason={type(e).__name__}")
        return False
    _face_authenticated = False
    _face_names = {0: os.getenv("FACE_RECOGNITION_USER_NAME", "User")}
    stop_evt = threading.Event()
    _face_recognizer_instance = FaceRecognizer(
        stop_event=stop_evt,
        model_path=os.getenv("FACE_RECOGNITION_MODEL", "trainingData.yml"),
        names=_face_names,
        auth_gate=_env_bool("FACE_RECOGNITION_AUTH_GATE", False),
    )
    _face_recognition_thread = threading.Thread(
        target=_run_face_recognition, args=(_face_recognizer_instance,), daemon=True, name="face-recognition"
    )
    _face_recognition_thread.start()
    gate_str = "true" if _env_bool("FACE_RECOGNITION_AUTH_GATE", False) else "false"
    print(f"[FACE] recognition_started auth_gate={gate_str}", flush=True)
    return True


def face_auth_blocking(timeout_s: int = 30) -> bool:
    """Run face recognition on the *calling* thread so the OpenCV preview
    window (`cv2.imshow`) displays correctly.  Blocks until the face is
    authenticated or *timeout_s* seconds elapse.  Releases the camera when
    done so the UI process can open it later.

    Returns True if authenticated, False otherwise.
    """
    global _face_recognizer_instance, _face_recognition_thread
    try:
        from engine.camera_control.face_recognizer import FaceRecognizer
    except Exception as e:
        print(f"[FACE] import_error reason={type(e).__name__}", flush=True)
        return False

    stop_evt = threading.Event()
    _face_recognizer_instance = FaceRecognizer(
        stop_event=stop_evt,
        model_path=os.getenv("FACE_RECOGNITION_MODEL", "trainingData.yml"),
        names={0: os.getenv("FACE_RECOGNITION_USER_NAME", "User")},
        auth_gate=True,
    )
    _face_recognition_thread = None  # not used — we run on the caller thread

    _face_recognizer_instance._auth_min_detections = int(
        os.getenv("FACE_RECOGNITION_AUTH_MIN_DETECTIONS", "5") or "5"
    )

    def _run_with_timeout():
        _face_recognizer_instance.run()

    t = threading.Thread(target=_run_with_timeout, daemon=True, name="face-auth-blocking")
    t.start()

    deadline = time.time() + timeout_s
    authenticated = False
    while t.is_alive() and time.time() < deadline:
        if _face_recognizer_instance.authenticated:
            authenticated = True
            break
        time.sleep(0.2)

    _face_recognizer_instance.stop()
    t.join(timeout=2.0)
    _face_recognizer_instance = None

    if authenticated:
        print("[FACE] authenticated — proceeding", flush=True)
    else:
        print(f"[FACE] timeout after {timeout_s}s — proceeding without auth", flush=True)
    return authenticated


def _run_face_recognition(recognizer):
    try:
        recognizer.run()
    except Exception as e:
        print(f"[FACE] run_error reason={type(e).__name__}")


def stop_face_recognition() -> bool:
    global _face_recognizer_instance, _face_recognition_thread
    if _face_recognizer_instance is None:
        return False
    _face_recognizer_instance.stop()
    if _face_recognition_thread and _face_recognition_thread.is_alive():
        _face_recognition_thread.join(timeout=2.0)
    _face_recognizer_instance = None
    _face_recognition_thread = None
    print("[FACE] stopped")
    return True


def is_face_recognition_running() -> bool:
    if _face_recognizer_instance is None:
        return False
    if _face_recognition_thread is None:
        return False
    return _face_recognition_thread.is_alive()


def face_authenticated() -> bool:
    if _face_recognizer_instance is not None:
        return _face_recognizer_instance.authenticated
    return _face_authenticated


def register_face(name: str = "User", duration_s: int = 10) -> bool:
    try:
        from engine.camera_control.face_recognizer import register_new_face
        return register_new_face(name=name, duration_s=duration_s)
    except Exception as e:
        print(f"[FACE] register_error reason={type(e).__name__}")
        return False


# ── Auto-start on import if env vars say so ────────────────────────────────
def _auto_start():
    if CAMERA_CONTROL_ENABLED and CAMERA_CONTROL_MODE in ("hand", "eye", "hybrid"):
        print(f"[CAMERA] auto_start mode={CAMERA_CONTROL_MODE}")
        start_camera_control(CAMERA_CONTROL_MODE)


if CAMERA_ON_STARTUP:
    _auto_start()

if _env_bool("FACE_RECOGNITION_ON_STARTUP", True):
    start_face_recognition()
