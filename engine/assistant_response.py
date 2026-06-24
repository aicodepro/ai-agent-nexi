from __future__ import annotations

import re
from typing import Any

from engine.tts_response_manager import build_spoken_text


QUESTION_STARTS = (
    "what", "which", "where", "when", "do you", "should i", "want me", "tell me",
)

QUESTION_PHRASES = (
    "which topic", "what should i", "what should", "where should i", "where should",
    "do you want", "would you like", "please provide", "tell me the", "want the full version",
)

_RHETORICAL_PHRASES = (
    "how can i help",
    "what can i do for you",
    "what can i do for ya",
    "is there anything else",
    "what would you like me to do",
    "what else can i help",
    "anything else i can help",
    "how else can i help",
    "did that answer your question",
    "does that answer your question",
    "does that help",
    "how does that sound",
)

ACTION_SUCCESS_RE = re.compile(
    r"^\s*(done|opened|opening|created|copied|saved|deleted|sent|launched|started)\b"
    r"|^\s*i\s+(opened|created|copied|saved|deleted|sent|launched|started)\b"
    r"|^\s*(the|your)\s+.+\s+(was\s+)?(opened|created|copied|saved|deleted|sent|launched|started)\b",
    re.IGNORECASE,
)


def response_asks_question(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return False
    lower = value.lower().strip()
    if any(phrase in lower for phrase in _RHETORICAL_PHRASES):
        return False
    if lower.endswith("?"):
        return True
    return lower.startswith(QUESTION_STARTS) or any(phrase in lower for phrase in QUESTION_PHRASES)


def infer_followup_type(text: str) -> str:
    lower = str(text or "").lower()
    if "which app" in lower:
        return "open_app"
    if "which website" in lower or "which site" in lower:
        return "open_website"
    if "what should i search" in lower:
        return "web_search"
    if "which topic" in lower:
        return "essay_topic"
    if "name the file" in lower:
        return "file_name"
    if "name the folder" in lower or "name it" in lower:
        return "folder_name"
    if "where should" in lower or "where do" in lower:
        return "folder_location"
    if "yes or no" in lower or lower.startswith("do you") or lower.startswith("should i"):
        return "confirmation"
    return "generic"


def make_response(
    display_text: str,
    spoken_text: str | None = None,
    expects_user_reply: bool = False,
    followup_question: str = "",
    followup_type: str = "",
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    display = str(display_text or "")
    asks = expects_user_reply or response_asks_question(display)
    question = followup_question or (display if asks else "")
    ftype = followup_type or (infer_followup_type(question) if asks else "")
    return {
        "display_text": display,
        "spoken_text": spoken_text if spoken_text is not None else build_spoken_text(display),
        "expects_user_reply": bool(asks),
        "followup_question": question,
        "followup_type": ftype,
        "source": source or "assistant",
        "ui_state_after": "listening" if asks else "idle",
        "metadata": metadata or {},
    }


def verified_action(tool_result: dict[str, Any] | None) -> bool:
    return bool(tool_result and tool_result.get("success") is True and tool_result.get("verified") is True)


def looks_like_action_success(text: str) -> bool:
    return bool(ACTION_SUCCESS_RE.search(str(text or "")))


def guard_unverified_action_message(text: str, tool_result: dict[str, Any] | None = None) -> str:
    if verified_action(tool_result):
        return str(text or "")
    if looks_like_action_success(text):
        print("[HALLUCINATION_GUARD] blocked_unverified_action", flush=True)
        return "I couldn't verify that action, so I won't claim it completed."
    return str(text or "")
