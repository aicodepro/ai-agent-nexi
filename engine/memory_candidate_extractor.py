"""
Memory Candidate Extractor

Implements intelligent extraction of durable, useful facts from conversations
for long-term memory storage.

Key features:
- Categorizes memory candidates by type (preferences, projects, etc.)
- Applies scoring based on confidence and value
- Filters out sensitive or low-value content
- Integrates with safety system
- Configurable extraction policies

Usage:
    from engine.memory_candidate_extractor import extract_memory_candidates
"""

from __future__ import annotations

from typing import Any

from engine.memory_safety import is_safe_to_store

# Candidate categories
CANDIDATE_CATEGORIES = {
    "identity": 0.9,  # High priority - name, basic info
    "preferences": 0.8,  # High priority - user likes/dislikes
    "projects": 0.8,  # High priority - current work
    "current_tasks": 0.7,  # Medium priority - ongoing tasks
    "corrections": 0.7,  # Medium priority - corrections
    "tool_failures": 0.6,  # Medium priority - failures
    "successful_workflows": 0.6,  # Medium priority - successes
    "ui_preferences": 0.6,  # Medium priority - UI settings
    "output_preferences": 0.6,  # Medium priority - output format
    "voice_preferences": 0.6,  # Medium priority - voice settings
    "model_preferences": 0.6,  # Medium priority - model settings
    "file_preferences": 0.6,  # Medium priority - file settings
}

# Extraction triggers (low-signal)
EXTRACTION_TRIGGERS = {
    "explicit": [  # High confidence triggers
        r"remember that",
        r"from now on",
        r"always ",
        r"don't ",
        r"do not ",
        r"i prefer",
        r"my name is",
        r"use this style",
    ],
    "correction": [  # Medium confidence triggers
        r"actually",
        r"this is wrong",
        r"that's wrong",
        r"that is wrong",
        r"next time",
        r"no,",
        r"i want",
    ],
    "information": [  # Low confidence triggers
        r"project",
        r"repo",
        r"workspace",
        r"model",
        r"gemini",
        r"groq",
        r"voice",
        r"speak",
        r"speech",
        r"ui",
        r"interface",
        r"screen",
        "short",
        "long",
        "copy code",
        "markdown",
        "tts failed",
        "tool failed",
        "didn't work",
        "did not work",
    ],
}

# Minimum confidence thresholds for storage
MIN_CONFIDENCE_FOR_STORAGE = 0.7
MIN_CONFIDENCE_FOR_CATEGORY = {
    "identity": 0.9,
    "preferences": 0.8,
    "projects": 0.8,
    "current_tasks": 0.7,
    "corrections": 0.7,
    "tool_failures": 0.6,
    "successful_workflows": 0.6,
    "ui_preferences": 0.6,
    "output_preferences": 0.6,
    "voice_preferences": 0.6,
    "model_preferences": 0.6,
    "file_preferences": 0.6,
}

# Maximum text length for storage
MAX_TEXT_LENGTH = 1000


def _detect_category_and_confidence(user_text: str, assistant_text: str) -> tuple[str, float]:
    """Detect category and assign confidence score.

    Args:
        user_text: User message text
        assistant_text: Assistant response text

    Returns:
        Tuple of (category, confidence_score)
    """
    combined = f"{user_text} {assistant_text}".lower()

    # Default category and confidence
    category = "preferences"
    confidence = 0.5

    # Check explicit triggers first (high confidence)
    for trigger in EXTRACTION_TRIGGERS["explicit"]:
        if trigger in combined:
            # Find which category this trigger belongs to
            for cat, trig_list in {
                "identity": ["my name is"],
                "preferences": ["i prefer"],
                "projects": ["project", "repo", "workspace"],
                "corrections": ["actually", "this is wrong", "that's wrong", "no,"],
                "current_tasks": ["next time"],
            }.items():
                if any(t in combined for t in trig_list):
                    category = cat
                    confidence = 1.0
                    return category, confidence

    # Check correction triggers
    for trigger in EXTRACTION_TRIGGERS["correction"]:
        if trigger in combined:
            category = "corrections"
            confidence = 0.8
            return category, confidence

    # Check information triggers
    for trigger in EXTRACTION_TRIGGERS["information"]:
        if trigger in combined:
            category = _infer_category_from_text(combined)
            confidence = 0.6
            return category, confidence

    # Special pattern for short/long preferences
    if "short" in combined and ("answer" in combined or "reply" in combined or "direct" in combined):
        category = "preferences"
        confidence = 0.9
    elif "long" in combined and ("box" in combined or "workspace" in combined or "main ui" in combined):
        category = "output_preferences"
        confidence = 0.9
    elif "copy code" in combined:
        category = "output_preferences"
        confidence = 0.9
    elif "markdown" in combined:
        category = "file_preferences"
        confidence = 0.9
    elif any(term in combined for term in ("tts failed", "tool failed", "didn't work", "did not work")):
        category = "tool_failures"
        confidence = 0.8
    elif any(term in combined for term in ("created", "done", "completed", "saved", "copied")):
        category = "successful_workflows"
        confidence = 0.8
    elif any(term in combined for term in ("model", "gemini", "groq")):
        category = "model_preferences"
        confidence = 0.8
    elif any(term in combined for term in ("voice", "speak", "speech")):
        category = "voice_preferences"
        confidence = 0.8
    elif any(term in combined for term in ("ui", "interface", "screen")):
        category = "ui_preferences"
        confidence = 0.8

    return category, confidence


def _infer_category_from_text(text: str) -> str:
    """Infer category from text when triggers match.

    Args:
        text: Combined user+assistant text (lowercase)

    Returns:
        Inferred category
    """
    if "my name is" in text:
        return "identity"
    elif "project" in text or "repo" in text or "workspace" in text:
        return "projects"
    elif "model" in text or "gemini" in text or "groq" in text:
        return "model_preferences"
    elif "voice" in text or "speak" in text or "speech" in text:
        return "voice_preferences"
    elif "ui" in text or "interface" in text or "screen" in text:
        return "ui_preferences"
    elif "short" in text and ("answer" in text or "reply" in text or "direct" in text):
        return "preferences"
    elif "long" in text and ("box" in text or "workspace" in text or "main ui" in text):
        return "output_preferences"
    elif "copy code" in text:
        return "output_preferences"
    elif "markdown" in text:
        return "file_preferences"
    elif any(term in text for term in ("tts failed", "tool failed", "didn't work", "did not work")):
        return "tool_failures"
    elif any(term in text for term in ("created", "done", "completed", "saved", "copied")):
        return "successful_workflows"
    else:
        return "preferences"


def _calculate_extraction_score(user_text: str, assistant_text: str, category: str) -> float:
    """Calculate extraction score based on multiple factors.

    Args:
        user_text: User message text
        assistant_text: Assistant response text
        category: Detected category

    Returns:
        Score between 0.0 and 1.0
    """
    combined = f"{user_text} {assistant_text}"

    # Base score from category
    base_score = CANDIDATE_CATEGORIES.get(category, 0.5)

    # Length penalty (very long text = lower score)
    length_penalty = min(len(combined) / 2000.0, 0.2)

    # Repetition penalty
    word_count = len(combined.split())
    repetition_penalty = min(word_count / 500.0, 0.2)

    # Calculate final score
    score = base_score - length_penalty - repetition_penalty

    # Ensure score is within bounds
    return max(0.0, min(1.0, score))


def extract_memory_candidates(user_text: str, assistant_text: str) -> list[dict[str, Any]]:
    """Extract memory candidates from user-assistant exchange.

    Args:
        user_text: User message text
        assistant_text: Assistant response text

    Returns:
        List of candidate memory dictionaries
    """
    # Skip if either text is empty
    if not user_text and not assistant_text:
        return []

    # Clean and validate text
    user_text = _clean_text(user_text)
    assistant_text = _clean_text(assistant_text)

    if not user_text and not assistant_text:
        return []

    # Check if safe to store
    if not is_safe_to_store(user_text)[0] and not is_safe_to_store(assistant_text)[0]:
        return []

    # Detect category and confidence
    category, confidence = _detect_category_and_confidence(user_text, assistant_text)

    # Calculate extraction score
    extraction_score = _calculate_extraction_score(user_text, assistant_text, category)

    # Apply minimum confidence threshold
    if extraction_score < MIN_CONFIDENCE_FOR_STORAGE:
        return []

    # Determine if we should extract based on score and confidence
    if extraction_score < 0.6 and confidence < 0.7:
        return []

    # Create candidate dictionary
    candidate = {
        "text": _format_candidate_text(user_text, assistant_text, category),
        "type": category,
        "source": _determine_source(user_text, assistant_text),
        "confidence": extraction_score,
        "original_user_text": user_text,
        "original_assistant_text": assistant_text,
        "timestamp": _now(),
    }

    return [candidate]


def _format_candidate_text(user_text: str, assistant_text: str, category: str) -> str:
    """Format candidate text for storage.

    Args:
        user_text: User message text
        assistant_text: Assistant response text
        category: Detected category

    Returns:
        Formatted text for storage
    """
    if category == "identity":
        # Extract name from text
        name_match = re.search(r"my name is (\w+)", user_text.lower())
        if name_match:
            return f"User's name is {name_match.group(1)}."

    elif category == "preferences":
        # Extract preference from text
        if "short" in user_text.lower() and ("answer" in user_text.lower() or "reply" in user_text.lower() or "direct" in user_text.lower()):
            return "User prefers short and direct answers."
        elif "long" in user_text.lower() and ("box" in user_text.lower() or "workspace" in user_text.lower() or "main ui" in user_text.lower()):
            return "User prefers long answers in the Jarvis Output Workspace."

    elif category == "output_preferences":
        if "copy code" in user_text.lower():
            return "User prefers code to be copied by default when requested."
        elif "markdown" in user_text.lower():
            return "User prefers markdown files for saved generated content."

    elif category == "tool_failures":
        return user_text

    elif category == "corrections":
        return user_text

    elif category == "successful_workflows":
        return f"User: {user_text} -> Jarvis: {assistant_text}"

    # Default: combine user and assistant text
    return f"{user_text} {assistant_text}".strip()


def _determine_source(user_text: str, assistant_text: str) -> str:
    """Determine source of the memory candidate.

    Args:
        user_text: User message text
        assistant_text: Assistant response text

    Returns:
        Source identifier
    """
    combined = f"{user_text} {assistant_text}".lower()

    if any(term in combined for term in ("actually", "this is wrong", "that's wrong", "no,")):
        return "correction"
    elif any(term in combined for term in ("remember that", "from now on")):
        return "explicit"
    else:
        return "implicit"


def _now() -> str:
    """Get current timestamp."""
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _clean_text(text: str) -> str:
    """Clean and validate text for extraction.

    Args:
        text: Raw text to clean

    Returns:
        Cleaned text, or empty string if unsafe/empty
    """
    if not text:
        return ""

    # Import here to avoid circular imports
    from engine.memory_safety import redact_sensitive, is_safe_to_store

    # Redact sensitive content
    value = redact_sensitive(str(text))

    # Check if safe to store
    safe, reason = is_safe_to_store(value)
    if not safe:
        return ""

    # Normalize whitespace
    import re

    value = re.sub(r"\s+", " ", value).strip()

    # Apply length limit
    return value[:MAX_TEXT_LENGTH]
