from __future__ import annotations

import re
import unicodedata
import os

COMMAND_WORDS = {
    "open", "search", "google", "find", "create", "make", "new", "folder", "file",
    "take", "note", "screenshot", "capture", "remember", "forget", "show", "what",
    "who", "where", "when", "why", "how", "tell", "explain", "play", "pause", "stop",
    "sleep", "wake", "activate", "hello", "hi", "bye", "goodbye", "thanks", "nexi",
    "calculate", "compute",
}

SHORT_FOLLOWUP_ANSWERS = {
    "chrome", "youtube", "desktop", "yes", "no", "cancel", "ronaldo",
    "ai agents", "notepad", "documents", "downloads",
}
FILLER_WORDS = {"um", "uh", "hmm", "mm", "erm"}


def clean_transcript(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" \t\r\n\"'")


def allow_short_followup_answers() -> bool:
    value = (os.getenv("TRANSCRIPT_ALLOW_SHORT_FOLLOWUP", "true") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def is_short_followup_answer(text: str) -> bool:
    t = clean_transcript(text).lower().rstrip(".?!")
    if not t:
        return False
    if t in FILLER_WORDS:
        return False
    if t in SHORT_FOLLOWUP_ANSWERS:
        return True
    words = re.findall(r"[a-zA-Z]+", t)
    return 1 <= len(words) <= 3 and len(t) <= 32


def accepts_pending_followup_answer(text: str) -> bool:
    return allow_short_followup_answers() and is_short_followup_answer(text)


def _letters(text: str):
    return [c for c in text if c.isalpha()]


def _latin_ratio(text: str) -> float:
    letters = _letters(text)
    if not letters:
        return 0.0
    latin = 0
    for c in letters:
        try:
            name = unicodedata.name(c)
        except ValueError:
            name = ""
        if "LATIN" in name and ord(c) < 128:
            latin += 1
    return latin / len(letters)


def _has_non_ascii_letter(text: str) -> bool:
    return any(c.isalpha() and ord(c) > 127 for c in text or "")


def is_probably_english_command(text: str) -> bool:
    t = clean_transcript(text)
    if not t:
        return False
    if _latin_ratio(t) < 0.85:
        return False
    if _has_non_ascii_letter(t):
        return False
    words = re.findall(r"[a-zA-Z]+", t.lower())
    if not words:
        return bool(re.search(r"\d\s*[+\-*/x]\s*\d", t))
    if len(t) <= 6 and not (set(words) & COMMAND_WORDS):
        return False
    if len(words) <= 2 and not (set(words) & COMMAND_WORDS):
        return False
    return True


def is_gibberish_or_wrong_language(text: str) -> bool:
    return not is_probably_english_command(text)
