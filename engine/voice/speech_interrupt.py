import os
import re


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
    t = re.sub(r"[^\w\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    raw_phrases = os.getenv(
        "NEXI_HOTWORD_PHRASES", os.getenv("NEXI_HOTWORD_PHRASE", "hey nexi,nexi")
    )
    wake_phrases = sorted(
        (re.sub(r"[^\w\s]", " ", phrase.lower()).strip() for phrase in raw_phrases.split(",")),
        key=len,
        reverse=True,
    )
    for phrase in wake_phrases:
        if phrase and t.startswith(phrase + " "):
            t = t[len(phrase):].strip()
            break
    for prefix in (
        "can you please ", "could you please ", "would you please ", "will you please ",
        "can you ", "could you ", "would you ", "will you ", "please ",
    ):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
            break
    if t.endswith(" please"):
        t = t[:-7].strip()
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
        if re.match(rf"^(?:i said\s+)?{re.escape(pattern)}(?:\s|$)", normalized):
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
