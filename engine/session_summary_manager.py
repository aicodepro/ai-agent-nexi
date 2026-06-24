"""
Session Summary Manager

Implements deterministic rolling summary for older conversation exchanges beyond the last 10.

Key features:
- Extracts and preserves key information from completed exchanges
- Builds extractive summaries (facts, decisions, plans, errors)
- Maintains bounded memory of older conversation history
- Integrates with autonomous exchange memory system
- Filters sensitive content before summarization

Usage:
    from engine.session_summary_manager import (
        merge_exchange,
        merge_exchanges,
        get_summary,
        reset_summary,
        build_summary_context,
    )
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive

# Configuration constants
MAX_SUMMARY_AGE_EXCHANGES = 11  # Number of exchanges before triggering summary
MAX_SUMMARY_LENGTH = 5000  # Maximum characters for rolling summary
MAX_SUMMARY_TEXT_LENGTH = 1000  # Maximum text per summary entry

# Summary categories
SUMMARY_CATEGORIES = {
    "facts": [],  # Factual information learned
    "decisions": [],  # Decisions made
    "plans": [],  # Plans or tasks
    "errors": [],  # Errors or failures
    "successful_actions": [],  # Successful actions
    "corrections": [],  # Corrections or changes
    "preferences": [],  # User preferences discovered
}


def _now() -> str:
    """Get current timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def _clean_text(text: str) -> str:
    """Clean and validate text for storage.

    Args:
        text: Raw text to clean

    Returns:
        Cleaned text, or empty string if unsafe/empty
    """
    if not text or not str(text).strip():
        return ""

    # Redact sensitive content
    value = redact_sensitive(str(text))

    # Check if safe to store
    safe, reason = is_safe_to_store(value)
    if not safe:
        print(f"[SESSION_SUMMARY] skipped reason={reason}", flush=True)
        return ""

    # Normalize whitespace
    value = re.sub(r"\s+", " ", value).strip()

    return value[:MAX_SUMMARY_TEXT_LENGTH]


def _detect_summary_category(user_text: str, assistant_text: str) -> str:
    """Detect which category an exchange belongs to.

    Args:
        user_text: User message text
        assistant_text: Assistant response text

    Returns:
        Summary category name
    """
    combined = f"{user_text} {assistant_text}".lower()

    # Facts: questions and answers about information
    if (
        "what is" in combined
        or "what are" in combined
        or "who is" in combined
        or "when" in combined
        or "where" in combined
        or "how many" in combined
        or "how much" in combined
    ):
        return "facts"

    # Decisions: action-related language
    if (
        "decide" in combined
        or "choose" in combined
        or "select" in combined
        or "pick" in combined
        or "going to" in combined
        or "will " in combined
        or "should " in combined
    ):
        return "decisions"

    # Plans: future-oriented language
    if (
        "plan" in combined
        or "next step" in combined
        or "upcoming" in combined
        or "future" in combined
        or "later" in combined
        or "following" in combined
    ):
        return "plans"

    # Errors: failure-related language
    if (
        "error" in combined
        or "failed" in combined
        or "fail" in combined
        or "mistake" in combined
        or "wrong" in combined
        or "bug" in combined
        or "issue" in combined
    ):
        return "errors"

    # Successful actions
    if (
        "created" in combined
        or "done" in combined
        or "completed" in combined
        or "saved" in combined
        or "copied" in combined
        or "opened" in combined
    ):
        return "successful_actions"

    # Corrections: change-related language
    if (
        "actually" in combined
        or "correction" in combined
        or "correct" in combined
        or "change" in combined
        or "fix" in combined
        or "update" in combined
        or "next time" in combined
    ):
        return "corrections"

    # Preferences: preference-related language
    if (
        "prefer" in combined
        or "like" in combined
        or "dislike" in combined
        or "want" in combined
        or "hate" in combined
    ):
        return "preferences"

    # Default to facts
    return "facts"


def _summarize_exchange(exchange: dict[str, Any]) -> str:
    """Create a summary entry for an exchange.

    Args:
        exchange: Exchange dictionary with user_text and assistant_text

    Returns:
        Summary entry string
    """
    user_text = exchange.get("user_text", "")
    assistant_text = exchange.get("assistant_text", "")

    if not user_text and not assistant_text:
        return ""

    category = _detect_summary_category(user_text, assistant_text)

    summary_parts = []

    if user_text:
        # Extract key phrases from user text
        user_summary = _extract_key_phrases(user_text)
        summary_parts.append(f"User asked: {user_summary}")

    if assistant_text:
        # Extract key phrases from assistant text
        assistant_summary = _extract_key_phrases(assistant_text)
        summary_parts.append(f"Jarvis responded: {assistant_summary}")

    # Add category
    summary_parts.append(f"Category: {category}")

    return " | ".join(summary_parts)


def _extract_key_phrases(text: str) -> str:
    """Extract key phrases from text.

    Args:
        text: Text to extract phrases from

    Returns:
        Key phrases string
    """
    # Simple key phrase extraction
    # Take first 3-5 words as representative
    words = text.split()
    if len(words) <= 5:
        return text

    # Use first 3 words and last 2 words as representative
    first_part = " ".join(words[:3])
    last_part = " ".join(words[-2:])

    return f"{first_part}...{last_part}"


def merge_exchange(exchange: dict[str, Any]) -> None:
    """Merge an exchange into the session summary.

    Args:
        exchange: Exchange dictionary with user_text and assistant_text
    """
    # Skip if no content
    if not exchange.get("user_text") and not exchange.get("assistant_text"):
        return

    # Clean and validate the exchange
    user_text = _clean_text(exchange.get("user_text", ""))
    assistant_text = _clean_text(exchange.get("assistant_text", ""))

    if not user_text and not assistant_text:
        return

    # Update the exchange with cleaned text
    exchange["user_text"] = user_text
    exchange["assistant_text"] = assistant_text

    # Create summary entry
    summary_entry = _summarize_exchange(exchange)
    if not summary_entry:
        return

    # Add to appropriate category in the global summary
    category = _detect_summary_category(user_text, assistant_text)

    # Save to persistent storage
    _save_summary()


def merge_exchanges(exchanges: list[dict[str, Any]]) -> None:
    """Merge multiple exchanges into the session summary.

    Args:
        exchanges: List of exchange dictionaries
    """
    for exchange in exchanges:
        merge_exchange(exchange)


def get_summary() -> dict[str, Any]:
    """Get the current session summary.

    Returns:
        Summary dictionary with categories
    """
    return _load_summary()


def reset_summary() -> None:
    """Reset the session summary to empty."""
    # Clear all summary categories
    for category in SUMMARY_CATEGORIES:
        SUMMARY_CATEGORIES[category].clear()

    # Save empty summary
    _save_summary()


def build_summary_context(max_chars: int = 2000) -> str:
    """Build context string from the session summary.

    Args:
        max_chars: Maximum characters for context

    Returns:
        Context string
    """
    summary = get_summary()

    context_parts = []

    for category, entries in summary.items():
        if not entries:
            continue

        context_parts.append(f"[{category.upper()}]:")
        for entry in entries[:10]:  # Limit entries per category
            context_parts.append(f"- {entry}")

    context = "\n".join(context_parts)
    return context[:max_chars]


# Persistent storage
_SUMMARY_PATH = "data/session_summary.json"


def _load_summary() -> dict[str, Any]:
    """Load summary from persistent storage."""
    import json
    from pathlib import Path

    summary_path = Path(_SUMMARY_PATH)
    if not summary_path.exists():
        return _empty_summary()

    try:
        with summary_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure all categories exist
        result = _empty_summary()
        for category in result:
            if category in data:
                result[category] = data[category]

        return result

    except Exception:
        return _empty_summary()


def _save_summary() -> None:
    """Save summary to persistent storage."""
    import json
    from pathlib import Path

    summary_path = Path(_SUMMARY_PATH)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(SUMMARY_CATEGORIES, f, indent=2)
    except Exception:
        pass


def _empty_summary() -> dict[str, Any]:
    """Create empty summary dictionary."""
    return {category: [] for category in SUMMARY_CATEGORIES}
