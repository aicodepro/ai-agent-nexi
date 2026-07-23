from __future__ import annotations

import re


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def build_spoken_text(display_text: str, max_chars: int = 700) -> str:
    """Return short voice text while preserving full UI display text elsewhere."""
    value = _clean(display_text)
    if len(value) <= max_chars:
        return value
    lowered = value.lower()
    kind = "recipe" if "recipe" in lowered else "answer"
    prefix = "Here's the short version. "
    suffix = f" I've put the full {kind} on screen."
    excerpt_limit = min(220, max_chars - len(prefix) - len(suffix) - 3)
    excerpt = value[:excerpt_limit].rsplit(" ", 1)[0].rstrip(".,;: ")
    return f"{prefix}{excerpt}...{suffix}"


def split_tts_chunks(text: str, max_chars: int = 260) -> list[str]:
    value = _clean(text)
    if not value:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", value)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not piece:
            continue
        if len(piece) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for index in range(0, len(piece), max_chars):
                chunk = piece[index:index + max_chars].strip()
                if chunk:
                    chunks.append(chunk)
            continue
        if current and len(current) + len(piece) + 1 > max_chars:
            chunks.append(current.strip())
            current = piece
        else:
            current = (current + " " + piece).strip()
    if current:
        chunks.append(current.strip())
    return chunks


def speak_interruptible(text: str, source: str = "tts") -> None:
    from engine.command import speak

    speak(text)
