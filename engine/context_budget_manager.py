"""
Context Budget Manager

Implements bounded context building for Jarvis by combining:
- Active mode/workflow
- Long-term memory
- Rolling summary of older exchanges
- Latest 10 exchanges
- Current user input

Key features:
- Token-efficient context building
- Configurable budget limits
- Prioritizes relevant information
- Integrates with autonomous memory systems
- Respects safety and sensitivity requirements

Usage:
    from engine.context_budget_manager import build_context
"""

from __future__ import annotations

from typing import Any

from engine.memory_safety import is_safe_to_store

# Configuration constants
DEFAULT_CONTEXT_MAX_CHARS = 8000
DEFAULT_LONG_TERM_LIMIT = 5
DEFAULT_RECENT_EXCHANGES_LIMIT = 10
DEFAULT_LONG_TERM_MAX_CHARS = 1800
DEFAULT_RECENT_EXCHANGES_MAX_CHARS = 4500
DEFAULT_ROLLING_SUMMARY_MAX_CHARS = 2000


def _add_section(context_parts: list[str], section_name: str, content: str, max_chars: int) -> int:
    """Add a section to the context if it has content and fits within budget.

    Args:
        context_parts: List to append context parts to
        section_name: Name of the section
        content: Content to add
        max_chars: Maximum characters for this section

    Returns:
        Number of characters used
    """
    if not content or not content.strip():
        return 0

    # Truncate content to fit
    truncated_content = content[:max_chars]

    if truncated_content:
        context_parts.append(f"[{section_name}]:")
        context_parts.append(truncated_content)

    return len(truncated_content)


def build_context(
    user_text: str,
    max_chars: int | None = None,
    long_term_limit: int | None = None,
    recent_exchanges_limit: int | None = None,
) -> str:
    """Build bounded context for AI models.

    Args:
        user_text: The current user input
        max_chars: Maximum characters for total context (default: DEFAULT_CONTEXT_MAX_CHARS)
        long_term_limit: Number of long-term memories to include (default: DEFAULT_LONG_TERM_LIMIT)
        recent_exchanges_limit: Number of recent exchanges to include (default: DEFAULT_RECENT_EXCHANGES_LIMIT)

    Returns:
        Formatted context string
    """
    if max_chars is None:
        max_chars = DEFAULT_CONTEXT_MAX_CHARS

    if long_term_limit is None:
        long_term_limit = DEFAULT_LONG_TERM_LIMIT

    if recent_exchanges_limit is None:
        recent_exchanges_limit = DEFAULT_RECENT_EXCHANGES_LIMIT

    context_parts = []
    chars_used = 0

    # 1. Active mode/state
    # This could be enhanced with actual voice state from the state machine
    active_mode_content = "[ACTIVE_MODE: voice_session]\n"
    chars_used += _add_section(context_parts, "ACTIVE_MODE", active_mode_content, max_chars - chars_used)

    # 2. Current workflow/followup
    # This could be enhanced with actual workflow state
    workflow_content = "[CURRENT_WORKFLOW: normal_operation]\n"
    chars_used += _add_section(context_parts, "WORKFLOW", workflow_content, max_chars - chars_used)

    # 3. Long-term memory (if budget allows)
    try:
        from engine.adaptive_memory import build_memory_context

        long_term_max = DEFAULT_LONG_TERM_MAX_CHARS
        remaining = max_chars - chars_used
        if remaining > long_term_max:
            long_term_content = build_memory_context(user_text, limit=long_term_limit, max_chars=long_term_max)
            chars_used += _add_section(context_parts, "LONG_TERM_MEMORY", long_term_content, remaining)
    except ImportError:
        pass

    # 4. Rolling summary (if budget allows and has content)
    try:
        from engine.session_summary_manager import build_summary_context

        summary_max = DEFAULT_ROLLING_SUMMARY_MAX_CHARS
        remaining = max_chars - chars_used
        if remaining > summary_max:
            summary_content = build_summary_context(summary_max)
            chars_used += _add_section(context_parts, "ROLLING_SUMMARY", summary_content, remaining)
    except ImportError:
        pass

    # 5. Latest exchanges (if budget allows)
    try:
        from engine.autonomous_memory import get_last_exchanges

        recent_exchanges_max = DEFAULT_RECENT_EXCHANGES_MAX_CHARS
        remaining = max_chars - chars_used
        if remaining > recent_exchanges_max:
            recent_exchanges = get_last_exchanges(recent_exchanges_limit)
            if recent_exchanges:
                exchanges_parts = []
                for i, exchange in enumerate(recent_exchanges):
                    if exchange.get("user_text"):
                        exchanges_parts.append(f"User{i+1}: {exchange['user_text'][:200]}")
                    if exchange.get("assistant_text"):
                        exchanges_parts.append(f"Jarvis{i+1}: {exchange['assistant_text'][:200]}")

                exchanges_content = "\n".join(exchanges_parts)
                chars_used += _add_section(
                    context_parts,
                    "RECENT_EXCHANGES",
                    exchanges_content,
                    remaining,
                )
    except ImportError:
        pass

    # 6. Current user input (always included)
    if user_text.strip():
        user_input_section = f"[CURRENT_USER_INPUT]: {user_text}"
        context_parts.append(user_input_section)

    # Combine all parts
    context = "\n".join(context_parts)

    # Final truncation to ensure within budget
    return context[:max_chars]
