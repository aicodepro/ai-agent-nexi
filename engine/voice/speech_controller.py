import threading
import queue
import os
import re
import tempfile
import time
import uuid

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
_ENGINE_LOCK = threading.RLock()

_state = {
    "is_speaking": False,
    "queue_size": 0,
    "last_text_preview": "",
    "last_stop_reason": "",
    "state": "idle",
}


def _get_engine():
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            if _HAS_CTYPES:
                ctypes.windll.ole32.CoInitialize(None)
            _ENGINE = pyttsx3.init("sapi5")
            voices = _ENGINE.getProperty("voices")
            if voices:
                voice_id = voices[0].id
                for v in voices:
                    vl = (v.name or "").lower()
                    if "zira" in vl or "natural" in vl or "neural" in vl:
                        voice_id = v.id
                        break
                _ENGINE.setProperty("voice", voice_id)
            _ENGINE.setProperty("rate", 160)
        return _ENGINE


def _safe_eel_call(function_name, *args):
    try:
        getattr(eel, function_name)(*args)
    except Exception as exc:
        print(f"[TTS] eel_call_failed function={function_name} reason={type(exc).__name__}", flush=True)


def _speak_pyttsx3(text):
    try:
        _safe_eel_call("DisplayMessage", text)
        _safe_eel_call("receiverText", text)
        with _ENGINE_LOCK:
            engine = _get_engine()
            engine.say(text)
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


def _play_audio_file_impl(file_path):
    from playsound import playsound
    playsound(file_path)


def _worker():
    global _state
    while True:
        item = _QUEUE.get()
        if item is None:
            _QUEUE.task_done()
            break
        if isinstance(item, dict):
            text = str(item.get("text") or "")
            item_kind = str(item.get("kind") or "speech")
            lifecycle_session_id = str(item.get("session_id") or "")
            lifecycle_global_lease_id = str(item.get("global_lease_id") or "")
            lifecycle_producer_id = str(item.get("producer_id") or "")
            lifecycle_started = bool(item.get("lifecycle_started", False))
        else:
            text = str(item or "")
            item_kind = "speech"
            lifecycle_session_id = ""
            lifecycle_global_lease_id = ""
            lifecycle_producer_id = ""
            lifecycle_started = False
        if _STOP_EVENT.is_set():
            if lifecycle_started:
                try:
                    if lifecycle_session_id:
                        from engine.runtime_bridge import notify_cooldown_complete, notify_tts_interrupted
                        if notify_tts_interrupted(lifecycle_session_id, lifecycle_producer_id):
                            notify_cooldown_complete(lifecycle_session_id, lifecycle_producer_id)
                    else:
                        from engine.runtime_bridge import notify_global_cooldown_complete, notify_global_tts_interrupted
                        if notify_global_tts_interrupted(lifecycle_global_lease_id):
                            notify_global_cooldown_complete(lifecycle_global_lease_id)
                except Exception:
                    pass
            _QUEUE.task_done()
            continue
        heartbeat_stop = threading.Event()
        heartbeat_thread = None
        if lifecycle_started:
            try:
                heartbeat_seconds = max(0.01, float(os.getenv("NEXI_TTS_HEARTBEAT_SECONDS", "5.0")))

                def _heartbeat():
                    from engine.runtime_bridge import notify_global_tts_heartbeat, notify_tts_heartbeat
                    while not heartbeat_stop.wait(heartbeat_seconds):
                        posted = (
                            notify_tts_heartbeat(lifecycle_session_id, lifecycle_producer_id)
                            if lifecycle_session_id
                            else notify_global_tts_heartbeat(lifecycle_global_lease_id)
                        )
                        if not posted:
                            return

                heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True, name="speech-controller-heartbeat")
                heartbeat_thread.start()
            except Exception as exc:
                print(f"[TTS] lifecycle_heartbeat_failed reason={type(exc).__name__}", flush=True)
        with _SPEAKER_LOCK:
            _state["is_speaking"] = True
            _state["state"] = "speaking"
            _state["last_text_preview"] = _redact_preview(text)
            _state["last_stop_reason"] = ""
        try:
            if item_kind == "audio_file":
                _play_audio_file_impl(text)
            else:
                _speak_impl(text)
        except Exception as e:
            print(f"Speech worker error: {e}")
        finally:
            if lifecycle_started:
                heartbeat_stop.set()
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=0.25)
                interrupted = _STOP_EVENT.is_set()
                try:
                    if lifecycle_session_id:
                        from engine.runtime_bridge import (
                            notify_cooldown_complete,
                            notify_tts_finished,
                            notify_tts_interrupted,
                        )
                        terminal_posted = (
                            notify_tts_interrupted(lifecycle_session_id, lifecycle_producer_id)
                            if interrupted
                            else notify_tts_finished(lifecycle_session_id, lifecycle_producer_id)
                        )
                        cooldown_callback = lambda: notify_cooldown_complete(lifecycle_session_id, lifecycle_producer_id)
                    else:
                        from engine.runtime_bridge import (
                            notify_global_cooldown_complete,
                            notify_global_tts_finished,
                            notify_global_tts_interrupted,
                        )
                        terminal_posted = (
                            notify_global_tts_interrupted(lifecycle_global_lease_id)
                            if interrupted
                            else notify_global_tts_finished(lifecycle_global_lease_id)
                        )
                        cooldown_callback = lambda: notify_global_cooldown_complete(lifecycle_global_lease_id)
                    if terminal_posted:
                        from engine.post_tts_cleanup import post_tts_cleanup
                        post_tts_cleanup(on_complete=cooldown_callback)
                    else:
                        print(f"[TTS] terminal_enqueue_failed session={lifecycle_session_id} lease={lifecycle_global_lease_id}", flush=True)
                        if lifecycle_session_id:
                            from engine.runtime_bridge import current_control_queue, post_session_finish
                            post_session_finish(
                                current_control_queue(),
                                lifecycle_session_id,
                                reason="tts_terminal_enqueue_failed",
                                force=True,
                            )
                except Exception as exc:
                    print(f"[TTS] lifecycle_terminal_failed reason={type(exc).__name__}", flush=True)
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
        reset_stop_flag()
    try:
        from engine.runtime_bridge import (
            current_bridge_session_id,
            notify_global_tts_started,
            notify_tts_started,
        )
        session_id = current_bridge_session_id()
        producer_id = uuid.uuid4().hex
        if session_id:
            global_lease_id = ""
            lifecycle_started = notify_tts_started(session_id, producer_id)
        else:
            global_lease_id = notify_global_tts_started()
            lifecycle_started = bool(global_lease_id)
    except Exception:
        session_id = ""
        producer_id = ""
        global_lease_id = ""
        lifecycle_started = False
    _ensure_worker()
    _QUEUE.put({
        "kind": "speech",
        "text": text,
        "session_id": session_id,
        "producer_id": producer_id,
        "global_lease_id": global_lease_id,
        "lifecycle_started": lifecycle_started,
    })
    with _SPEAKER_LOCK:
        _state["queue_size"] = _QUEUE.qsize()


def play_audio_file(file_path):
    if not file_path:
        return
    try:
        from engine.runtime_bridge import notify_global_tts_started
        global_lease_id = notify_global_tts_started()
        lifecycle_started = bool(global_lease_id)
    except Exception:
        global_lease_id = ""
        lifecycle_started = False
    _ensure_worker()
    _QUEUE.put({
        "kind": "audio_file",
        "text": str(file_path),
        "session_id": "",
        "producer_id": "",
        "global_lease_id": global_lease_id,
        "lifecycle_started": lifecycle_started,
    })
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
                except Exception as exc:
                    print(f"[TTS] pyttsx3_stop_failed reason={type(exc).__name__}", flush=True)
                try:
                    _ENGINE.endLoop()
                except Exception as exc:
                    print(f"[TTS] pyttsx3_end_loop_failed reason={type(exc).__name__}", flush=True)
    except Exception as exc:
        print(f"[TTS] pyttsx3_stop_failed reason={type(exc).__name__}", flush=True)
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
