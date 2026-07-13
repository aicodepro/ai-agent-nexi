import multiprocessing
import os
import time
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
try:
    from engine.debug_trace import install_clean_console_filter
    install_clean_console_filter()
except Exception:
    pass
try:
    from engine.no_window import install as _install_no_window
    _install_no_window()  # suppress console/PowerShell window flashes (Windows)
except Exception:
    pass

try:
    from engine.demo_mode import DemoMode
    if DemoMode.is_active():
        print("=" * 56, flush=True)
        print("  === NEXI DEMO MODE ===", flush=True)
        print("  Presentations & live demos — safe, scripted execution", flush=True)
        print("=" * 56, flush=True)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent

schedule_file = BASE_DIR / "schedule.txt"
alarm_file = BASE_DIR / "Alarm_data.txt"


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _face_auth_gate() -> bool:
    """Block until the authorised user's face is recognised.

    Opens the camera and runs LBPH face recognition in an **infinite loop**
    until the user's face matches (confidence below threshold). Press **q**
    to abort.  Nexi will NOT start without a recognised face.

    Returns:
        ``True`` if the user was authenticated.
        ``False`` if auth failed (camera error, missing model, or user
        pressed q) — the caller MUST exit when this returns ``False``.
    """
    if not _env_bool("FACE_RECOGNITION_ON_STARTUP", True):
        print("[FACE] disabled by env — skipping auth gate")
        return True
    auth_gate = os.getenv("FACE_RECOGNITION_AUTH_GATE", "true").lower() == "true"
    if not auth_gate:
        print("[FACE] auth_gate disabled — skipping")
        return True
    threshold = int(os.getenv("FACE_RECOGNITION_CONFIDENCE_THRESHOLD", "60"))
    user_name = os.getenv("FACE_RECOGNITION_USER_NAME", "User")
    print(f"[FACE] auth_gate enabled — face rec starting (threshold={threshold}) ...")
    try:
        import cv2
        import FaceRecognition as fr

        face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        model = None
        for p in ("trainingData.yml", os.path.join(BASE_DIR, "trainingData.yml"),
                  r"E:\jarvis-main\trainingData.yml"):
            if os.path.exists(p):
                model = p
                break
        if model is None:
            print("[FACE] trainingData.yml not found — cannot authenticate", flush=True)
            return False
        face_recognizer.read(model)
        name = {0: user_name}
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[FACE] camera_open_failed — cannot authenticate", flush=True)
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        frame_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                faces_detected, gray_img = fr.faceDetection(frame)
                for face in faces_detected:
                    x, y, w, h = face
                    fr.draw_rect(frame, face)
                    roi_gray = gray_img[y:y + w, x:x + h]
                    if roi_gray.size == 0:
                        continue
                    try:
                        label, confidence = face_recognizer.predict(roi_gray)
                    except Exception:
                        continue
                    predicted_name = name.get(label, "Unknown")
                    print(f"[FACE] label={label} confidence={confidence:.0f} name={predicted_name} threshold={threshold}", flush=True)
                    if confidence < threshold:
                        print(f"[FACE] authenticated — proceeding (confidence={confidence:.0f} < threshold={threshold})", flush=True)
                        cap.release()
                        cv2.destroyAllWindows()
                        return True

                cv2.putText(frame, "Look at the camera — face auth required", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 255), 2)
                cv2.imshow("Face Recognition - Press Q to quit", frame)
                frame_count += 1

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("[FACE] user cancelled — q pressed", flush=True)
                    cap.release()
                    cv2.destroyAllWindows()
                    return False
        finally:
            cap.release()
            cv2.destroyAllWindows()
    except Exception as e:
        print(f"[FACE] gate_error reason={type(e).__name__} message={e} — cannot authenticate", flush=True)
    return False


def _fatal_pipeline_failure(reason: str, stop_event=None):
    print(f"[WAKEPROC] fatal pipeline failed reason={reason}", flush=True)
    while stop_event is not None and not stop_event.is_set():
        time.sleep(1.0)
    return False


def startNexi(command_queue=None, stop_event=None):
    print(f"[RUN] ui_process starting pid={os.getpid()} cwd={os.getcwd()} queue={'yes' if command_queue is not None else 'no'}", flush=True)
    from main import main
    main(command_queue=command_queue, stop_event=stop_event)


def _signal_audio_ready(audio_ready, reason: str) -> None:
    """Unblock the UI process once the voice stack is up (or has given up).

    Set on success (model + VAD + mic open) AND on every failure path so the
    UI never waits the full timeout when audio can't start.
    """
    if audio_ready is not None and not audio_ready.is_set():
        print(f"[WAKEPROC] audio_ready signalled reason={reason}", flush=True)
        audio_ready.set()


def listenHotword(command_queue=None, stop_event=None, audio_ready=None):
    print(f"[RUN] audio_process starting pid={os.getpid()} cwd={os.getcwd()} queue={'yes' if command_queue is not None else 'no'}", flush=True)
    backend = (os.getenv("VOICE_WAKE_BACKEND", "") or "").lower().strip()
    legacy_fallback_disabled = _env_bool("DISABLE_LEGACY_HOTWORD_FALLBACK", False)
    print(f"[WAKEPROC] backend={backend or 'legacy'} pid={os.getpid()} queue={'yes' if command_queue is not None else 'no'}", flush=True)
    print(f"[WAKEPROC] legacy_fallback_disabled={str(legacy_fallback_disabled).lower()}", flush=True)

    if backend == "openwakeword":
        pipeline_reason = "not_started"
        try:
            from engine.audio_wake_pipeline import (
                start_audio_wake_pipeline,
                is_pipeline_running,
                get_last_start_error,
            )
            print("[WAKE] pipeline start requested", flush=True)
            start_audio_wake_pipeline(command_queue=command_queue)
            if is_pipeline_running():
                print("[WAKEPROC] pipeline running blocking=True", flush=True)
                # Voice recognition (openWakeWord model, Silero VAD, mic) is now
                # fully loaded — release the UI so it launches against a ready stack.
                _signal_audio_ready(audio_ready, "pipeline_running")
                while True:
                    if stop_event is not None and stop_event.is_set():
                        break
                    time.sleep(1.0)
                return
            pipeline_reason = get_last_start_error() or "not_running"
            print(f"[WAKEPROC] pipeline failed reason={pipeline_reason}", flush=True)
        except Exception as e:
            pipeline_reason = type(e).__name__
            print(f"[WAKEPROC] pipeline unavailable reason={pipeline_reason}", flush=True)

        if legacy_fallback_disabled:
            _signal_audio_ready(audio_ready, f"fatal:{pipeline_reason}")
            return _fatal_pipeline_failure(pipeline_reason, stop_event)

        print(f"[WAKEPROC] WARNING legacy fallback activated reason={pipeline_reason}", flush=True)

    # Legacy path (Porcupine optional, SpeechRecognition default)
    from engine.features import hotword_no_key, start_clap_if_enabled
    start_clap_if_enabled()
    _signal_audio_ready(audio_ready, "legacy_backend")
    hotword_no_key()


import threading

if __name__ == '__main__':
    if not _face_auth_gate():
        print("[FATAL] Face authentication required — exiting", flush=True)
        sys.exit(1)
    os.environ["FACE_RECOGNITION_ON_STARTUP"] = "false"

    command_queue = multiprocessing.Queue()
    stop_event = multiprocessing.Event()
    audio_ready = multiprocessing.Event()
    print(f"[BRIDGE] queue created id={id(command_queue)} pid={os.getpid()}", flush=True)

    p1 = multiprocessing.Process(target=startNexi, args=(command_queue, stop_event))
    p2 = multiprocessing.Process(target=listenHotword, args=(command_queue, stop_event, audio_ready))

    p3 = None
    p4 = None

    try:
        from Time_operation.throw_alert import check_schedule, check_alarm
        if schedule_file.exists():
            p3 = multiprocessing.Process(target=check_schedule, args=(str(schedule_file),))
            p3.start()
        else:
            print(f"[SCHEDULE] File not found: {schedule_file} — skipped")
        if alarm_file.exists():
            p4 = multiprocessing.Process(target=check_alarm, args=(str(alarm_file),))
            p4.start()
        else:
            print(f"[ALARM] File not found: {alarm_file} — skipped")
    except ImportError as e:
        print(f"[SCHEDULE] Import error: {e} — schedule/alarm skipped")

    try:
        # Start the audio process FIRST and wait until the voice-recognition
        # stack (openWakeWord model + Silero VAD + mic) is fully loaded before
        # launching the UI, so the UI opens against a ready, responsive backend.
        p2.start()
        print(f"[RUN] audio_process spawned pid={p2.pid}", flush=True)

        ready_timeout = float(os.getenv("NEXI_AUDIO_READY_TIMEOUT", "30") or "30")
        print(f"[RUN] waiting for voice stack ready (timeout={ready_timeout}s)...", flush=True)
        ready = audio_ready.wait(timeout=ready_timeout)
        print(f"[RUN] audio_ready={str(ready).lower()} — launching UI", flush=True)

        p1.start()
        print(f"[RUN] ui_process spawned pid={p1.pid}", flush=True)

        p1.join()
        if p3 is not None:
            p3.join()
        if p4 is not None:
            p4.join()
    except KeyboardInterrupt:
        print("[RUNTIME] shutdown requested")
    finally:
        stop_event.set()
        if p2.is_alive():
            p2.terminate()
            p2.join()
