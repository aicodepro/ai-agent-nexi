"""UI state machine — canonical states, aliases, labels, and Eel emission."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

CANONICAL_STATES = {"sleep", "wake_detected", "listening", "waiting_for_speech",
                    "recognising", "thinking", "saying", "error"}

STATE_ALIASES = {
    "idle": "sleep", "standby": "sleep", "ready": "sleep",
    "hearing_speech": "listening", "recording": "listening",
    "transcribing": "recognising", "processing": "thinking",
    "speaking": "saying", "responding": "saying",
}

STATE_LABELS = {
    "sleep": "Standby", "wake_detected": "Wake Detected",
    "listening": "Listening", "waiting_for_speech": "Waiting for Speech",
    "recognising": "Recognising", "thinking": "Thinking",
    "saying": "Speaking", "error": "Error",
}


def canonical_state(state: str) -> str:
    s = state.strip().lower()
    return STATE_ALIASES.get(s, s) if s not in CANONICAL_STATES else s


def label_for(state: str, source: str = "") -> str:
    cs = canonical_state(state)
    if cs == "wake_detected" and source:
        return f"Wake ({source})"
    return STATE_LABELS.get(cs, cs.title())


@dataclass
class UIStateEvent:
    state: str
    source: str = ""
    text: str = ""
    status: str = ""
    label: str = ""
    created_at: float = field(default_factory=time.time)

    def to_payload(self) -> dict:
        return {"state": self.state, "source": self.source,
                "text": (self.text or "")[:120], "status": self.status or self.state,
                "label": self.label or label_for(self.state, self.source)}


class UIStateManager:
    def __init__(self, dedupe_ms: int = 250):
        self._last_state = ""
        self._last_time = 0.0
        self._dedupe_s = dedupe_ms / 1000.0

    def emit(self, state: str, source: str = "", text: str = "", status: str = "") -> None:
        cs = canonical_state(state)
        now = time.time()
        if cs == self._last_state and (now - self._last_time) < self._dedupe_s:
            return
        self._last_state = cs
        self._last_time = now
        evt = UIStateEvent(state=cs, source=source, text=text, status=status or cs,
                           label=label_for(cs, source))
        self._post_to_eel(evt)
        level = "debug" if cs == "sleep" else "info"
        print(f"[UI] state={cs} source={source} level={level}", flush=True)

    def _post_to_eel(self, evt: UIStateEvent) -> None:
        try:
            import eel
            eel.updateNexiState(json.dumps(evt.to_payload()))
        except Exception:
            pass

    def reset(self):
        self._last_state = ""
        self._last_time = 0.0


_manager = UIStateManager()


def emit_state(state: str, source: str = "", text: str = "", status: str = "") -> None:
    _manager.emit(state, source, text, status)


def safe_eel_call(function_name: str, *args) -> bool:
    try:
        import eel
        fn = getattr(eel, function_name)
        fn(*args)
        return True
    except Exception:
        return False
