"""Configurable non-speech lifecycle cues for blind and low-vision users."""
from __future__ import annotations

import os
import threading


STATE_EARCONS = {
    "sleep": "sleep",
    "online": "wake",
    "listening": "listening",
    "waiting_for_speech": "waiting",
    "recognising": "recognising",
    "thinking": "working",
    "saying": "speaking",
    "error": "error",
}

EARCON_PATTERNS = {
    "wake": ((660, 70), (880, 90)),
    "listening": ((880, 80),),
    "waiting": ((740, 55),),
    "recognising": ((740, 60), (740, 60)),
    "working": ((520, 55),),
    "speaking": ((620, 50),),
    "sleep": ((440, 80), (330, 100)),
    "error": ((220, 140), (220, 140)),
}


def earcon_for_state(state: str) -> str:
    return STATE_EARCONS.get(str(state or "").strip().lower(), "")


def earcons_enabled() -> bool:
    return os.getenv("NEXI_EARCONS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def play_earcon(state: str) -> bool:
    cue = earcon_for_state(state)
    pattern = EARCON_PATTERNS.get(cue)
    if not earcons_enabled() or not pattern:
        return False

    def _play() -> None:
        try:
            import winsound

            for frequency, duration in pattern:
                winsound.Beep(frequency, duration)
        except Exception:
            return

    threading.Thread(target=_play, name=f"earcon-{cue}", daemon=True).start()
    return True
