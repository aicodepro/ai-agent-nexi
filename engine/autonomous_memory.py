"""
Autonomous Exchange Memory

Implements the autonomous last-10-exchange memory system for Nexi.

Features:
- Stores the latest 10 user-assistant exchanges automatically
- Maintains raw exchanges and rolling summaries
- Provides bounded context building
- Integrates with existing memory systems (safety, adaptive, episodic)
- No manual user interaction required for storage

Usage:
    from engine.autonomous_memory import (
        add_user_message,
        add_assistant_message,
        get_last_exchanges,
        get_rolling_summary,
        build_context,
        clear_short_term,
    )
"""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive

# Configuration constants
LAST_EXCHANGE_LIMIT = 10  # Number of exchanges to store raw
ROLLING_SUMMARY_MAX_CHARS = 5000  # Maximum characters for rolling summary
MAX_EXCHANGE_CHARS = 4500  # Maximum chars per exchange
MAX_CONTEXT_CHARS = 8000  # Maximum characters for built context
MAX_EXCHANGE_TEXT_CHARS = 4500  # Maximum text per exchange

# Data structures
class Exchange:
    """Represents a single user-assistant exchange pair."""

    def __init__(
        self,
        user_text: str,
        assistant_text: str,
        user_source: str = "",
        assistant_source: str = "",
        user_metadata: dict | None = None,
        assistant_metadata: dict | None = None,
    ):
        self.user_text = user_text
        self.assistant_text = assistant_text
        self.user_source = user_source
        self.assistant_source = assistant_source
        self.user_metadata = user_metadata or {}
        self.assistant_metadata = assistant_metadata or {}
        self.timestamp = datetime.now().isoformat(timespec="seconds")
        self.is_complete = assistant_text is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert exchange to dictionary for serialization."""
        return {
            "user": self.user_text,
            "assistant": self.assistant_text,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "user_source": self.user_source,
            "assistant_source": self.assistant_source,
            "user_metadata": self.user_metadata,
            "assistant_metadata": self.assistant_metadata,
            "timestamp": self.timestamp,
            "is_complete": self.is_complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Exchange":
        """Create exchange from dictionary."""
        return cls(
            user_text=data.get("user_text", ""),
            assistant_text=data.get("assistant_text", ""),
            user_source=data.get("user_source", ""),
            assistant_source=data.get("assistant_source", ""),
            user_metadata=data.get("user_metadata", {}),
            assistant_metadata=data.get("assistant_metadata", {}),
        )

    def to_summary(self) -> str:
        """Convert exchange to a summary string."""
        summary_parts = []

        if self.user_text:
            summary_parts.append(f"User: {self.user_text[:200]}")
        if self.assistant_text:
            summary_parts.append(f"Nexi: {self.assistant_text[:200]}")

        return " | ".join(summary_parts)


class AutonomousExchangeMemory:
    """Manages the autonomous exchange memory with rolling summary.

    Key features:
    - Stores exactly LAST_EXCHANGE_LIMIT exchanges raw
    - Maintains a rolling summary of older exchanges
    - Only stores durable, useful facts in long-term memory
    - Automatically sanitizes and filters content
    - Provides bounded context building for AI models
    """

    def __init__(
        self,
        max_exchanges: int = LAST_EXCHANGE_LIMIT,
        max_summary_chars: int = ROLLING_SUMMARY_MAX_CHARS,
    ):
        # Deque for storing exchanges (automatically bounds size)
        self._exchanges: deque[Exchange] = deque(maxlen=max_exchanges)
        self._max_exchanges = max_exchanges
        self._max_summary_chars = max_summary_chars

        # Current incomplete exchange (when user message arrives before assistant response)
        self._current_exchange: Exchange | None = None

        # Rolling summary storage
        self._rolling_summary: str = ""

        # Statistics
        self._total_exchanges_processed = 0

    def add_user_message(self, text: str, source: str = "", metadata: dict | None = None) -> None:
        """Add a user message to the memory system.

        Args:
            text: The user message text
            source: Source of the message (e.g., "voice", "ui", "hotword")
            metadata: Additional metadata about the message
        """
        # Clean and validate the text
        cleaned_text = self._clean_text(text)
        if not cleaned_text:
            return

        # If we have an existing incomplete exchange, mark it as complete
        # by adding a placeholder assistant response
        if self._current_exchange is not None:
            self._current_exchange.assistant_text = ""
            self._current_exchange.is_complete = False
            self._finalize_exchange(self._current_exchange)

        # Create new current exchange
        self._current_exchange = Exchange(
            user_text=cleaned_text,
            assistant_text="",
            user_source=source,
            user_metadata=metadata or {},
        )

    def add_assistant_message(self, text: str, source: str = "", metadata: dict | None = None) -> None:
        """Add an assistant message to complete the current exchange.

        Args:
            text: The assistant response text
            source: Source of the response
            metadata: Additional metadata about the response
        """
        if self._current_exchange is None:
            # No current user message, store as standalone assistant response
            # This can happen with greeting/identity responses
            self._store_standalone_assistant(text, source, metadata)
            return

        # Complete the current exchange
        cleaned_text = self._clean_text(text)
        if not cleaned_text:
            # Assistant message is empty or unsafe, mark exchange as incomplete
            self._current_exchange.assistant_text = ""
            self._current_exchange.is_complete = False
            self._finalize_exchange(self._current_exchange)
            self._current_exchange = None
            return

        self._current_exchange.assistant_text = cleaned_text
        self._current_exchange.assistant_source = source
        self._current_exchange.assistant_metadata = metadata or {}
        self._current_exchange.is_complete = True

        # Finalize the exchange
        self._finalize_exchange(self._current_exchange)
        self._current_exchange = None

    def get_last_exchanges(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get the last N exchanges.

        Args:
            limit: Maximum number of exchanges to return (default: LAST_EXCHANGE_LIMIT)

        Returns:
            List of exchange dictionaries
        """
        if limit is None:
            limit = self._max_exchanges

        limit = min(limit, self._max_exchanges)
        return [exchange.to_dict() for exchange in list(self._exchanges)[-limit:]]

    def get_rolling_summary(self) -> str:
        """Get the rolling summary of older exchanges.

        Returns:
            The rolling summary string
        """
        return self._rolling_summary

    def get_current_incomplete(self) -> dict[str, Any] | None:
        """Get the current incomplete exchange (if any).

        Returns:
            Dictionary representation of the current incomplete exchange, or None
        """
        if self._current_exchange is None:
            return None
        return {
            "user_text": self._current_exchange.user_text,
            "user_source": self._current_exchange.user_source,
            "user_metadata": self._current_exchange.user_metadata,
            "timestamp": self._current_exchange.timestamp,
            "is_complete": False,
        }

    def has_current_incomplete(self) -> bool:
        """Check if there's a current incomplete exchange."""
        return self._current_exchange is not None

    def exchange_count(self) -> int:
        """Return the number of raw exchanges currently retained."""
        return len(self._exchanges)

    def build_context(
        self,
        user_text: str,
        max_chars: int | None = None,
        include_long_term: bool = True,
    ) -> str:
        """Build context for AI models from autonomous memory.

        Args:
            user_text: The current user input to contextualize
            max_chars: Maximum characters for context (default: MAX_CONTEXT_CHARS)
            include_long_term: Whether to include long-term memory

        Returns:
            Formatted context string
        """
        if max_chars is None:
            max_chars = MAX_CONTEXT_CHARS

        context_parts = []

        # 1. Active mode/state (simplified - could be enhanced)
        context_parts.append("[ACTIVE_MODE: voice_session]")

        # 2. Current workflow/followup (simplified)
        context_parts.append("[CURRENT_WORKFLOW: normal_operation]")

        # 3. Latest 10 exchanges — keep this early so bounded contexts always
        # include recent user/assistant turns before verbose summaries.
        recent_exchanges = self.get_last_exchanges()
        if recent_exchanges:
            context_parts.append("Recent exchanges:")
            for i, exchange in enumerate(recent_exchanges):
                if exchange.get("user_text"):
                    context_parts.append(f"User{i+1}: {exchange['user_text'][:200]}")
                if exchange.get("assistant_text"):
                    context_parts.append(f"Nexi{i+1}: {exchange['assistant_text'][:200]}")

        # 4. Relevant long-term memories (if enabled)
        if include_long_term:
            try:
                from engine.adaptive_memory import build_memory_context

                long_term_context = build_memory_context(user_text, limit=5, max_chars=1800)
                if long_term_context.strip():
                    context_parts.append("[LONG_TERM_MEMORY]:")
                    context_parts.append(long_term_context)
            except ImportError:
                pass

        # 5. Rolling summary (if any)
        if self._rolling_summary.strip():
            context_parts.append("[ROLLING_SUMMARY]:")
            context_parts.append(self._rolling_summary)

        # 6. Current user input (for context)
        if user_text.strip():
            context_parts.append(f"[CURRENT_USER_INPUT]: {user_text}")

        # Combine and truncate to max length
        context = "\n".join(context_parts)
        return context[:max_chars]

    def clear_short_term(self) -> None:
        """Clear short-term memory (exchanges and summary)."""
        self._exchanges.clear()
        self._current_exchange = None
        self._rolling_summary = ""

    def get_statistics(self) -> dict[str, Any]:
        """Get memory statistics.

        Returns:
            Dictionary with statistics
        """
        completed_exchanges = [ex for ex in self._exchanges if ex.is_complete]
        incomplete_exchanges = len([ex for ex in self._exchanges if not ex.is_complete])

        return {
            "total_exchanges_processed": self._total_exchanges_processed,
            "stored_exchanges": len(self._exchanges),
            "completed_exchanges": len(completed_exchanges),
            "incomplete_exchanges": incomplete_exchanges,
            "has_current_incomplete": self.has_current_incomplete(),
            "summary_length": len(self._rolling_summary),
        }

    # Private helper methods

    def _clean_text(self, text: str) -> str:
        """Clean and validate text for storage.

        Args:
            text: Raw text to clean

        Returns:
            Cleaned text, or empty string if unsafe/empty
        """
        if not text or not str(text).strip():
            return ""

        value = redact_sensitive(str(text))
        safe, reason = is_safe_to_store(value)
        if not safe:
            print(f"[AUTONOMOUS_MEMORY] skipped reason={reason}", flush=True)
            return ""

        # Normalize whitespace
        value = re.sub(r"\s+", " ", value).strip()

        # Apply length limit
        return value[:MAX_EXCHANGE_TEXT_CHARS]

    def _finalize_exchange(self, exchange: Exchange) -> None:
        """Finalize an exchange by adding it to storage and updating rolling summary.

        Args:
            exchange: The exchange to finalize
        """
        # Update rolling summary if needed
        self._update_rolling_summary(exchange)

        # Add to exchanges deque (automatically bounds size)
        self._exchanges.append(exchange)
        self._total_exchanges_processed += 1

        # Try to extract memory candidates
        try:
            from engine.memory_candidate_extractor import extract_memory_candidates
            from engine.memory_safety import is_safe_to_store

            # Extract candidates from this exchange
            candidates = extract_memory_candidates(exchange.user_text, exchange.assistant_text)

            for candidate in candidates:
                # Only store if safe and high-value
                if self._is_high_value_candidate(candidate) and is_safe_to_store(candidate["text"])[0]:
                    self._store_in_long_term_memory(candidate)

        except ImportError:
            pass

    def _update_rolling_summary(self, new_exchange: Exchange) -> None:
        """Update the rolling summary with a new exchange.

        Args:
            new_exchange: The new exchange to add to the summary
        """
        # Create summary entry for this exchange
        summary_entry = self._create_summary_entry(new_exchange)

        # Add to rolling summary
        if self._rolling_summary:
            self._rolling_summary += "\n" + summary_entry
        else:
            self._rolling_summary = summary_entry

        # Truncate if too long
        if len(self._rolling_summary) > self._max_summary_chars:
            # Keep the most recent summary entries
            summary_entries = self._rolling_summary.split("\n")
            truncated = "\n".join(summary_entries[-10:])  # Keep last 10 summary entries
            self._rolling_summary = truncated

    def _create_summary_entry(self, exchange: Exchange) -> str:
        """Create a summary entry for an exchange.

        Args:
            exchange: The exchange to summarize

        Returns:
            Summary entry string
        """
        parts = []

        if exchange.user_text:
            # Summarize user text (extract key nouns/phrases)
            user_summary = self._summarize_text(exchange.user_text)
            parts.append(f"User: {user_summary}")

        if exchange.assistant_text:
            # Summarize assistant text (extract key actions/decisions)
            assistant_summary = self._summarize_text(exchange.assistant_text)
            parts.append(f"Nexi: {assistant_summary}")

        # Add metadata if available
        if exchange.user_source:
            parts.append(f"  Source: {exchange.user_source}")

        return " | ".join(parts)

    def _summarize_text(self, text: str) -> str:
        """Summarize text for rolling summary.

        Args:
            text: Text to summarize

        Returns:
            Summary string
        """
        # Simple extractive summarization: extract key phrases
        words = text.split()
        if len(words) <= 10:
            return text

        # Take first 5 and last 5 words as representative
        first_part = " ".join(words[:5])
        last_part = " ".join(words[-5:])

        # Add some key indicators
        summary = f"{first_part}...{last_part}"

        # Remove adjacent duplicate words without invalid backrefs.
        summary = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", summary, flags=re.IGNORECASE)

        return summary

    def _is_high_value_candidate(self, candidate: dict[str, Any]) -> bool:
        """Check if a memory candidate is high-value.

        Args:
            candidate: Memory candidate dictionary

        Returns:
            True if candidate should be stored
        """
        # Check confidence
        confidence = candidate.get("confidence", 0.0)
        if confidence < 0.7:
            return False

        # Check type (prefer certain types)
        memory_type = candidate.get("type", "")
        high_value_types = {
            "preferences", "projects", "corrections", "identity", "current_tasks"
        }
        if memory_type not in high_value_types:
            return False

        # Check text length (not too long)
        text = candidate.get("text", "")
        if len(text) > 1000:
            return False

        return True

    def _store_standalone_assistant(self, text: str, source: str = "", metadata: dict | None = None) -> None:
        """Store a standalone assistant message (e.g., greetings, identity)."""
        # For standalone assistant messages, we still clean and store
        cleaned_text = self._clean_text(text)
        if not cleaned_text:
            return

        # Store as a special exchange with no user message
        exchange = Exchange(
            user_text="",
            assistant_text=cleaned_text,
            assistant_source=source,
            assistant_metadata=metadata or {},
        )
        exchange.is_complete = True

        # Add to exchanges (but don't count toward 10 exchange limit)
        self._exchanges.append(exchange)
        self._total_exchanges_processed += 1

        # Update rolling summary
        self._update_rolling_summary(exchange)

    def _store_in_long_term_memory(self, candidate: dict[str, Any]) -> None:
        """Store a candidate in long-term memory.

        Args:
            candidate: Memory candidate to store
        """
        try:
            from engine.adaptive_memory import remember

            remember(
                candidate["text"],
                memory_type=candidate["type"],
                source=candidate.get("source", "autonomous_extraction"),
                confidence=candidate.get("confidence", 1.0),
            )
        except ImportError:
            pass


# Global instance
_autonomous_memory: AutonomousExchangeMemory | None = None


def get_autonomous_memory() -> AutonomousExchangeMemory:
    """Get the global autonomous memory instance."""
    global _autonomous_memory
    if _autonomous_memory is None:
        _autonomous_memory = AutonomousExchangeMemory()
    return _autonomous_memory


# Public API functions
def add_user_message(text: str, source: str = "", metadata: dict | None = None) -> None:
    """Add a user message to autonomous memory.

    Args:
        text: The user message text
        source: Source of the message (e.g., "voice", "ui", "hotword")
        metadata: Additional metadata about the message
    """
    get_autonomous_memory().add_user_message(text, source, metadata)


def add_assistant_message(text: str, source: str = "", metadata: dict | None = None) -> None:
    """Add an assistant message to autonomous memory.

    Args:
        text: The assistant response text
        source: Source of the response
        metadata: Additional metadata about the response
    """
    get_autonomous_memory().add_assistant_message(text, source, metadata)


def get_last_exchanges(limit: int | None = None) -> list[dict[str, Any]]:
    """Get the last N exchanges from autonomous memory.

    Args:
        limit: Maximum number of exchanges to return (default: LAST_EXCHANGE_LIMIT)

    Returns:
        List of exchange dictionaries
    """
    return get_autonomous_memory().get_last_exchanges(limit)


def get_rolling_summary() -> str:
    """Get the rolling summary from autonomous memory.

    Returns:
        The rolling summary string
    """
    return get_autonomous_memory().get_rolling_summary()


def build_context(
    user_text: str,
    max_chars: int | None = None,
    include_long_term: bool = True,
) -> str:
    """Build context from autonomous memory.

    Args:
        user_text: The current user input to contextualize
        max_chars: Maximum characters for context (default: MAX_CONTEXT_CHARS)
        include_long_term: Whether to include long-term memory

    Returns:
        Formatted context string
    """
    return get_autonomous_memory().build_context(user_text, max_chars, include_long_term)


def clear_short_term() -> None:
    """Clear short-term memory (exchanges and summary)."""
    get_autonomous_memory().clear_short_term()


def has_current_incomplete() -> bool:
    """Check if there's a current incomplete exchange.

    Returns:
        True if there's an incomplete exchange
    """
    return get_autonomous_memory().has_current_incomplete()


def get_current_incomplete() -> dict[str, Any] | None:
    """Get the current incomplete exchange.

    Returns:
        Dictionary representation of the current incomplete exchange, or None
    """
    return get_autonomous_memory().get_current_incomplete()


def get_statistics() -> dict[str, Any]:
    """Get autonomous memory statistics.

    Returns:
        Dictionary with statistics
    """
    return get_autonomous_memory().get_statistics()
