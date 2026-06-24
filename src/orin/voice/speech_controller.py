import threading
import queue
import os
import re
import tempfile
import time

try:
    import ctypes
    _HAS_CTYPES = True
except ImportError:
    _HAS_CTYPES = False

import pyttsx3
import eel


_SECRET_PATTERNS = [
    (re.compile(r'\b[A-Za-z0-9]{20,}\b', re.I), "[REDACTED_TOKEN]"),
    (re.compile(r'\b\d{16}\b'), "[REDACTED_CARD]"),
    (re.compile(r'\b\d{6}\b'), "[REDACTED_OTP]"),
    (re.compile(r'(?:password|passwd|pwd|secret|token|api[_-]?key|cookie|auth)\s*[=:]\s*\S+', re.I),
     "[REDACTED_SECRET]"),
]


def _redact_preview(text):
    if not text:
        return ""
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted[:80]


try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


_SPEAKER_LOCK = threading.Lock()
_QUEUE = queue.Queue()
_STOP_EVENT = threading.Event()
_WORKER_THREAD = None
_ENGINE = None
_ENGINE_LOCK = threading.Lock()

_state = {
    "is_speaking": False,
    "queue_size": 0,
    "last_text_preview": "",
    "last_stop_reason": "",
    "state": "idle",
}


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        if _HAS_CTYPES:
            ctypes.windll.ole32.CoInitialize(None)
        _ENGINE = pyttsx3.init("sapi5")
        voices = _ENGINE.getProperty("voices")
        if voices:
            _ENGINE.setProperty("voice", voices[0].id)
        _ENGINE.setProperty("rate", 174)
    return _ENGINE


def _safe_eel_call(function_name, *args):
    try:
        getattr(eel, function_name)(*args)
    except Exception:
        pass


def _speak_pyttsx3(text):
    try:
        engine = _get_engine()
        _safe_eel_call("DisplayMessage", text)
        engine.say(text)
        _safe_eel_call("receiverText", text)
        engine.runAndWait()
    except Exception as e:
        print(f"Speech controller pyttsx3 error: {e}")


def _speak_streamelements(text, voice="Aditi"):
    if not _HAS_REQUESTS:
        return False
    try:
        from playsound import playsound as _local_playsound
    except ImportError:
        print("[TTS] playsound not installed, cannot use StreamElements TTS")
        return False
    url = "https://api.streamelements.com/kappa/v2/speech"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    file_path = None
    try:
        _safe_eel_call("DisplayMessage", text)
        result = _requests.get(
            url=url,
            headers=headers,
            params={"voice": voice, "text": text},
            timeout=10,
        )
        result.raise_for_status()
        content_type = result.headers.get("content-type", "").lower()
        if not result.content or "audio" not in content_type:
            return False
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            file_path = f.name
            f.write(result.content)
        _local_playsound(file_path)
        _safe_eel_call("receiverText", text)
        return True
    except Exception as e:
        print(f"Speech controller StreamElements error: {e}")
        return False
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


def _speak_impl(text):
    if _STOP_EVENT.is_set():
        return
    online_tts = os.getenv("NEXI_ONLINE_TTS") == "1"
    if online_tts:
        ok = _speak_streamelements(text)
        if ok:
            return
    _speak_pyttsx3(text)


def _worker():
    global _state
    while True:
        item = _QUEUE.get()
        if item is None:
            _QUEUE.task_done()
            break
        text = item
        if _STOP_EVENT.is_set():
            _QUEUE.task_done()
            continue
        with _SPEAKER_LOCK:
            _state["is_speaking"] = True
            _state["state"] = "speaking"
            _state["last_text_preview"] = _redact_preview(text)
            _state["last_stop_reason"] = ""
        try:
            _speak_impl(text)
        except Exception as e:
            print(f"Speech worker error: {e}")
        finally:
            with _SPEAKER_LOCK:
                _state["is_speaking"] = bool(_QUEUE.qsize() > 0 and not _STOP_EVENT.is_set())
                _state["state"] = "idle" if not _state["is_speaking"] else "speaking"
                _state["queue_size"] = _QUEUE.qsize()
            _QUEUE.task_done()


def _ensure_worker():
    global _WORKER_THREAD
    if _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
        _WORKER_THREAD = threading.Thread(target=_worker, daemon=True, name="speech-worker")
        _WORKER_THREAD.start()


def speak(text, interrupt=False):
    if not text or not text.strip():
        return
    if interrupt:
        stop_speaking(reason="interrupted_by_new_speech")
    _ensure_worker()
    _QUEUE.put(text)
    with _SPEAKER_LOCK:
        _state["queue_size"] = _QUEUE.qsize()


def stop_speaking(reason="user_requested"):
    with _SPEAKER_LOCK:
        _state["last_stop_reason"] = reason
        _state["state"] = "stopping"
    _STOP_EVENT.set()
    try:
        with _ENGINE_LOCK:
            if _ENGINE is not None:
                try:
                    _ENGINE.stop()
                except Exception:
                    pass
                try:
                    _ENGINE.endLoop()
                except Exception:
                    pass
    except Exception:
        pass
    drained = 0
    while not _QUEUE.empty():
        try:
            _QUEUE.get_nowait()
            _QUEUE.task_done()
            drained += 1
        except queue.Empty:
            break
    with _SPEAKER_LOCK:
        _state["is_speaking"] = False
        _state["queue_size"] = 0
        _state["last_text_preview"] = ""
        _state["state"] = "idle"


def clear_queue():
    drained = 0
    while not _QUEUE.empty():
        try:
            _QUEUE.get_nowait()
            _QUEUE.task_done()
            drained += 1
        except queue.Empty:
            break
    with _SPEAKER_LOCK:
        _state["queue_size"] = 0
    return drained


def is_speaking():
    with _SPEAKER_LOCK:
        return _state["is_speaking"]


def get_state():
    with _SPEAKER_LOCK:
        return dict(_state)


def shutdown():
    stop_speaking(reason="shutdown")
    _QUEUE.put(None)
    global _WORKER_THREAD
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        _WORKER_THREAD.join(timeout=2)
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            try:
                _ENGINE.stop()
            except Exception:
                pass
            _ENGINE = None
        if _HAS_CTYPES:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass


def reset_stop_flag():
    _STOP_EVENT.clear()
    with _SPEAKER_LOCK:
        if _state["state"] == "stopping":
            _state["state"] = "idle"
