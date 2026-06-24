STOP_SPEAKING_PATTERNS = [
    "stop",
    "stop speaking",
    "stop talking",
    "enough",
    "cancel speech",
    "bas",
    "band karo",
    "chup",
    "chup ho jao",
    "ruk jao",
    "nexi stop",
]

EMERGENCY_STOP_PATTERNS = [
    "stop everything",
    "emergency stop",
    "sab band karo",
    "kill all tasks",
    "sab rok do",
    "freeze everything",
    "halt",
    "abort",
]


def normalize_stop_text(text):
    t = text.lower().strip()
    t = t.replace("nexi ", "").replace(" nexi", "")
    t = t.replace(".", "").replace(",", "").replace("!", "").replace("?", "")
    return t.strip()


def is_stop_speaking_command(text):
    if not text or not text.strip():
        return False
    normalized = normalize_stop_text(text)
    for pattern in STOP_SPEAKING_PATTERNS:
        if normalized == pattern:
            return True
    return False


def is_emergency_stop_command(text):
    if not text or not text.strip():
        return False
    normalized = normalize_stop_text(text)
    for pattern in EMERGENCY_STOP_PATTERNS:
        if pattern in normalized or normalized == pattern:
            return True
    return False


def classify_stop_command(text):
    if is_emergency_stop_command(text):
        return "emergency_stop"
    if is_stop_speaking_command(text):
        return "stop_speaking"
    return None


def classify_speech_control(text):
    if is_emergency_stop_command(text):
        return "emergency_stop"
    if is_stop_speaking_command(text):
        return "speech_stop"
    return "none"
