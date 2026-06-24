import threading
from datetime import datetime

from src.orin.memory.memory_policy import classify_memory_text
from src.orin.memory.memory_redaction import redact_sensitive


class ConversationBuffer:
    _max_turns = 5

    def __init__(self, max_turns=None):
        self._lock = threading.Lock()
        self._turns = []
        if max_turns and max_turns > 0:
            self._max_turns = max_turns

    def append_turn(self, user_text, assistant_text):
        user_processed = self._process_text(user_text)
        assistant_processed = self._process_text(assistant_text)

        turn = {
            "user": user_processed,
            "assistant": assistant_processed,
            "timestamp": datetime.now().isoformat(),
        }

        with self._lock:
            self._turns.append(turn)
            if len(self._turns) > self._max_turns:
                self._turns = self._turns[-self._max_turns:]

        return turn

    def get_turns(self):
        with self._lock:
            return list(self._turns)

    def get_context(self):
        return self.get_turns()

    def get_formatted_context(self):
        with self._lock:
            if not self._turns:
                return ""
            lines = []
            for turn in self._turns:
                lines.append(f"User: {turn['user']}")
                lines.append(f"Jarvis: {turn['assistant']}")
            return "\n".join(lines)

    def clear(self):
        with self._lock:
            self._turns.clear()

    def count(self):
        with self._lock:
            return len(self._turns)

    def to_dict(self):
        with self._lock:
            return {
                "turns": list(self._turns),
                "count": len(self._turns),
                "max_turns": self._max_turns,
            }

    @property
    def max_turns(self):
        return self._max_turns

    @classmethod
    def _process_text(cls, text):
        if not text or not isinstance(text, str):
            return ""
        decision, _ = classify_memory_text(text)
        if decision == "REJECT":
            return "[Content blocked]"
        return redact_sensitive(text)
