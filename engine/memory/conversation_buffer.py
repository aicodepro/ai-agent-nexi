import threading
import re
from datetime import datetime

from engine.memory.memory_policy import classify_memory_text
from engine.memory.memory_redaction import redact_sensitive


class ConversationBuffer:
    _max_turns = 5
    _max_summary_chars = 2000
    _max_text_chars = 1200
    _raw_capture_pattern = re.compile(
        r"(?i)(?:screen(?:shot|\s+(?:capture|dump))|ocr)\b.{0,40}\b(?:data|dump|contents|text|image|result)"
    )

    def __init__(self, max_turns=None):
        self._lock = threading.Lock()
        self._turns = []
        self._summary = ""
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
            while len(self._turns) > self._max_turns:
                evicted = self._turns.pop(0)
                text = f"User: {evicted['user']}\nNexi: {evicted['assistant']}"
                self._summary = (self._summary + "\n" + text).strip()[-self._max_summary_chars:]

        return turn

    def get_turns(self):
        with self._lock:
            return list(self._turns)

    def get_context(self):
        return self.get_turns()

    def get_summary(self):
        with self._lock:
            return self._summary

    def get_formatted_context(self):
        with self._lock:
            if not self._turns:
                return f"Earlier conversation summary:\n{self._summary}" if self._summary else ""
            lines = []
            if self._summary:
                lines.extend(["Earlier conversation summary:", self._summary])
            for turn in self._turns:
                lines.append(f"User: {turn['user']}")
                lines.append(f"Nexi: {turn['assistant']}")
            return "\n".join(lines)

    def clear(self):
        with self._lock:
            self._turns.clear()
            self._summary = ""

    def count(self):
        with self._lock:
            return len(self._turns)

    def to_dict(self):
        with self._lock:
            return {
                "turns": list(self._turns),
                "summary": self._summary,
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
        if cls._raw_capture_pattern.search(text):
            return "[Content blocked]"
        decision, _ = classify_memory_text(text)
        if decision == "REJECT":
            return "[Content blocked]"
        return redact_sensitive(text)[:cls._max_text_chars]
