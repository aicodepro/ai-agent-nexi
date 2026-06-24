import threading
import os
import socket
import subprocess
import eel
from engine.features import *
from engine.command import *
from engine.ui_loader import init_eel_ui
import datetime
from dotenv import load_dotenv

load_dotenv()
try:
    from engine.debug_trace import install_clean_console_filter
    install_clean_console_filter()
except Exception:
    pass

cv2 = None
face_authenticated = True
cap = None

face_recognition_enabled = os.getenv("FACE_RECOGNITION_ON_STARTUP", "false").lower() == "true"


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _find_free_port(host: str, preferred: int, max_port: int = 8020) -> tuple[int, str]:
    auto_port = _env_bool("JARVIS_UI_AUTO_PORT", True)
    if not auto_port:
        if _is_port_available(host, preferred):
            return preferred, ""
        return preferred, "in_use_but_auto_disabled"
    if _is_port_available(host, preferred):
        return preferred, ""
    kill_stale = _env_bool("JARVIS_KILL_STALE_UI_PORT", False)
    if kill_stale:
        try:
            import subprocess as _sp
            result = _sp.run(
                ["powershell", "-Command",
                 f"Get-NetTCPConnection -LocalPort {preferred} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {{ Stop-Process -Id $_ -Force }}"],
                capture_output=True, text=True, timeout=10
            )
            import time
            time.sleep(1)
            if _is_port_available(host, preferred):
                print(f"[UI_PORT] kill_stale succeeded for port={preferred}", flush=True)
                return preferred, ""
        except Exception:
            pass
    for port in range(preferred + 1, max_port + 1):
        if _is_port_available(host, port):
            print(f"[UI_PORT] requested={preferred} selected={port} reason={preferred}_in_use", flush=True)
            return port, f"{preferred}_in_use"
    raise RuntimeError(f"No free port found in range {preferred}-{max_port}")

if face_recognition_enabled:
    import cv2
    import FaceRecognition as fr

    try:
        face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        face_recognizer.read('trainingData.yml')
    except AttributeError:
        print("Error: 'cv2.face' module not available. Install opencv-contrib-python.")
        exit(1)

    name = {0: "Darsh"}
    cap = cv2.VideoCapture(0)
    face_authenticated = False

    def check_face(frame):
        global face_authenticated
        faces_detected, gray_img = fr.faceDetection(frame)
        for face in faces_detected:
            (x, y, w, h) = face
            roi_gray = gray_img[y:y+w, x:x+h]
            label, confidence = face_recognizer.predict(roi_gray)
            print(f"Label: {label}, Confidence: {confidence}")
            fr.draw_rect(frame, face)
            predicted_name = name.get(label, "Unknown")
            if confidence < 60:
                fr.put_text(frame, predicted_name, x, y)
                if predicted_name == "Darsh":
                    face_authenticated = True
                    break

    def recognize_faces():
        global face_authenticated
        while not face_authenticated:
            ret, frame = cap.read()
            if ret:
                check_face(frame)
                resized_img = cv2.resize(frame, (1000, 700))
                cv2.imshow('Face Recognition', resized_img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
else:
    print("Face recognition disabled by FACE_RECOGNITION_ON_STARTUP=false")

@eel.expose
def ui_submit_text(text):
    from engine.ui_adapter import submit_text
    return submit_text(text)

@eel.expose
def ui_submit_file_drop(file_paths):
    from engine.ui_adapter import submit_file_drop
    return submit_file_drop(file_paths)

@eel.expose
def ui_get_env_status():
    from engine.ui_adapter import get_env_status
    return get_env_status()

@eel.expose
def ui_get_runtime_status():
    from engine.ui_adapter import get_runtime_status
    return get_runtime_status()

@eel.expose
def ui_get_capabilities():
    from engine.ui_adapter import get_ui_capabilities
    return get_ui_capabilities()

@eel.expose
def ui_get_tool_categories():
    from engine.tool_category_view import get_tool_categories
    return get_tool_categories()

@eel.expose
def ui_get_suggestions():
    from engine.tool_category_view import get_command_suggestions
    return get_command_suggestions()

def _find_msedge() -> str | None:
    """Find msedge.exe path. Checks registry App Paths, then common install dirs."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as key:
            path = winreg.QueryValue(key, None)
            if path and os.path.isfile(path):
                return path
    except Exception:
        pass
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _launch_edge_in_thread(url: str, delay_ms: int = 1500) -> None:
    """Launch Edge in app mode after a delay so Eel server is ready."""
    def _launch():
        import time
        time.sleep(delay_ms / 1000.0)
        edge_path = _find_msedge()
        if edge_path is None:
            print(f"[UI] msedge not found — trying webbrowser fallback url={url}", flush=True)
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception as exc:
                print(f"[UI] webbrowser_fallback_failed reason={type(exc).__name__}", flush=True)
            return
        from engine.ui_loader import edge_window_args
        args = [edge_path, *edge_window_args(), f"--app={url}"]
        try:
            subprocess.Popen(args)
            print(f"[UI] edge_launched path={edge_path} args={' '.join(args[1:])}", flush=True)
        except Exception as exc:
            print(f"[UI] edge_launch_failed reason={type(exc).__name__} fallback=maximized", flush=True)
            try:
                subprocess.Popen([edge_path, "--start-maximized", f"--app={url}"])
            except Exception as exc2:
                print(f"[UI] edge_fallback_failed reason={type(exc2).__name__}", flush=True)
    threading.Thread(target=_launch, daemon=True).start()


def start_jarvis(command_queue=None, stop_event=None):
    print(f"[RUN] ui start_jarvis pid={os.getpid()} queue={'yes' if command_queue is not None else 'no'}", flush=True)
    init_eel_ui(eel)
    try:
        from engine.jarvis_wake_controller import set_wake_queue
        set_wake_queue(command_queue)
    except Exception as e:
        print(f"[WAKE] queue setup failed: {e}")
    if command_queue is not None:
        try:
            from engine.runtime_bridge import start_ui_bridge_pump
            start_ui_bridge_pump(command_queue, stop_event)
        except Exception as e:
            print(f"[BRIDGE] pump start failed: {e}")
    requested_port = _env_int("JARVIS_UI_PORT", 8000)
    host = "localhost"
    try:
        selected_port, reason = _find_free_port(host, requested_port)
    except RuntimeError as e:
        print(f"[UI_PORT] fatal: {e}", flush=True)
        return
    if reason:
        print(f"[UI_PORT] requested={requested_port} selected={selected_port} reason={reason}", flush=True)
    else:
        print(f"[UI_PORT] requested={requested_port} selected={selected_port} reason=free", flush=True)
    from engine.ui_loader import edge_window_args, get_window_mode, should_open_fullscreen
    url = f"http://{host}:{selected_port}/index.html"
    fullscreen = should_open_fullscreen()
    window_mode = get_window_mode()
    print(f"[UI] fullscreen={str(fullscreen).lower()}", flush=True)
    print(f"[UI] window_mode={window_mode}", flush=True)
    print(f"[RUN] eel.start pid={os.getpid()} host={host} port={selected_port}", flush=True)
    try:
        from engine.debug_trace import major
        major("JARVIS READY")
        major("SLEEPING")
    except Exception:
        pass
    _launch_edge_in_thread(url, delay_ms=1500)
    eel.start('index.html', mode=None, host=host, port=selected_port, block=True)

def greet_user():
    hour = int(datetime.datetime.now().hour)
    if hour >= 0 and hour < 12:
        speak("Good Morning!")
    elif hour >= 12 and hour < 18:
        speak("Good Afternoon!")
    else:
        speak("Good Evening!")
    speak("I am Jarvis. How may I help you, sir?")

def main(command_queue=None, stop_event=None):
    global face_authenticated
    if face_recognition_enabled:
        print("Starting face recognition...")
        recognize_thread = threading.Thread(target=recognize_faces)
        recognize_thread.start()
        recognize_thread.join()

    if face_authenticated:
        print("Face recognized. Starting Jarvis...")
        if _env_bool("TTS_BEFORE_COMMAND_CAPTURE", False):
            greet_user()
        else:
            print("[TTS] startup_greeting skipped reason=TTS_BEFORE_COMMAND_CAPTURE=false", flush=True)
        start_jarvis(command_queue=command_queue, stop_event=stop_event)

    if cap is not None:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
