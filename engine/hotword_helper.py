import os
import time
import struct

# ---- Hotword matcher (Task 1) ----
HOTWORD_VARIANTS = {"jarvis", "jervis", "jarves"}

def is_jarvis_hotword(text: str) -> bool:
    if not text or not text.strip():
        return False
    words = text.lower().strip().split()
    for word in words:
        if word in HOTWORD_VARIANTS:
            return True
    return False

# ---- Cooldown state (Task 2) ----
_last_hotword_at = 0.0
HOTWORD_COOLDOWN_SECONDS = 2.0
_is_awake = False

def check_hotword_cooldown() -> bool:
    global _last_hotword_at
    now = time.time()
    if now - _last_hotword_at < HOTWORD_COOLDOWN_SECONDS:
        print("[HOTWORD] cooldown active \u2014 ignored")
        return False
    _last_hotword_at = now
    return True

def set_hotword_awake(awake: bool):
    global _is_awake
    _is_awake = awake

def is_hotword_awake() -> bool:
    return _is_awake

def reset_hotword_cooldown():
    global _last_hotword_at
    _last_hotword_at = 0.0

def get_hotword_access_key():
    return os.getenv("PICOVOICE_ACCESS_KEY") or os.getenv("PORCUPINE_ACCESS_KEY") or ""

def is_porcupine_available():
    key = get_hotword_access_key()
    if not key:
        return False
    try:
        import pvporcupine
        return True
    except ImportError:
        return False

def get_hotword_backend():
    if is_porcupine_available():
        return "porcupine"
    return "speech_recognition"

def log_hotword_status():
    backend = get_hotword_backend()
    key_status = "present" if get_hotword_access_key() else "missing"
    print(f"[HOTWORD] backend={backend} picovoice_key={key_status}")
    return backend
