from __future__ import annotations

import os
import time
import builtins
from pathlib import Path
from typing import Any


_MAJOR_EVENTS = {
    "JARVIS READY",
    "SLEEPING",
    "HOTWORD DETECTED",
    "DOUBLE CLAP DETECTED",
    "ONLINE",
    "LISTENING",
    "RECOGNISING",
    "THINKING",
    "SAYING",
}

_last_major: dict[str, float] = {}
_ORIGINAL_PRINT = builtins.print
_FILTER_INSTALLED = False


def _debug_path() -> Path:
    configured = (os.getenv("JARVIS_DEBUG_LOG_FILE", "artifacts/jarvis_interview_debug.log") or "").strip()
    return Path(configured or "artifacts/jarvis_interview_debug.log")


def _console_clean() -> bool:
    return (os.getenv("JARVIS_CONSOLE_LOG_LEVEL", "normal") or "normal").strip().lower() == "clean"


def _format(event: str, fields: dict[str, Any]) -> str:
    if not fields:
        return event
    parts = [event]
    for key, value in fields.items():
        safe = str(value).replace("\n", " ")[:300]
        parts.append(f"{key}={safe}")
    return " ".join(parts)


def _append(line: str) -> None:
    try:
        path = _debug_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {line}\n")
    except Exception:
        pass


def major(event: str, **fields: Any) -> None:
    name = (event or "").strip().upper()
    line = _format(name, fields)
    _append(line)
    now = time.time()
    if now - _last_major.get(name, 0.0) < 0.25:
        return
    _last_major[name] = now
    if _console_clean() and name in _MAJOR_EVENTS:
        _ORIGINAL_PRINT(name, flush=True)
    elif not _console_clean():
        _ORIGINAL_PRINT(line, flush=True)


def detail(event: str, **fields: Any) -> None:
    _append(_format(event, fields))


def line(message: str) -> None:
    msg = str(message or "")
    detail("log", line=msg)
    if not _console_clean():
        _ORIGINAL_PRINT(msg, flush=True)
        return

    lower = msg.lower()
    if "jarvis ready" in lower or "pipeline running" in lower:
        major("JARVIS READY")
    elif "hotword detected" in lower or "[wake] detected source=hotword" in lower:
        major("HOTWORD DETECTED")
    elif "double_clap_detected=true" in lower or "double clap detected" in lower:
        major("DOUBLE CLAP DETECTED")
    elif "wake detected" in lower or "internal_wake" in lower:
        major("ONLINE")
    elif "listening" in lower and "finished" not in lower:
        major("LISTENING")
    elif "recognising" in lower or "recognizing" in lower or "asr_started" in lower or "request_started" in lower:
        major("RECOGNISING")
    elif "thinking" in lower or "dispatch_started" in lower:
        major("THINKING")
    elif "saying" in lower or "speak_started" in lower or "audio_output_started" in lower:
        major("SAYING")
    elif "sleep mode" in lower or "finish id=" in lower or "sleeping" in lower:
        major("SLEEPING")


def _event_from_message(message: str) -> str:
    lower = message.lower()
    if "jarvis ready" in lower or "pipeline running" in lower:
        return "JARVIS READY"
    if "hotword detected" in lower or "[wake] detected source=hotword" in lower:
        return "HOTWORD DETECTED"
    if "double_clap_detected=true" in lower or "double clap detected" in lower:
        return "DOUBLE CLAP DETECTED"
    if "wake detected" in lower or "internal_wake" in lower:
        return "ONLINE"
    if "listening" in lower and "finished" not in lower:
        return "LISTENING"
    if "recognising" in lower or "recognizing" in lower or "asr_started" in lower or "request_started" in lower:
        return "RECOGNISING"
    if "thinking" in lower or "dispatch_started" in lower:
        return "THINKING"
    if "saying" in lower or "speak_started" in lower or "audio_output_started" in lower:
        return "SAYING"
    if "sleep mode" in lower or "finish id=" in lower or "sleeping" in lower:
        return "SLEEPING"
    return ""


def install_clean_console_filter() -> None:
    global _FILTER_INSTALLED
    if _FILTER_INSTALLED or not _console_clean():
        return

    def _filtered_print(*args: Any, **kwargs: Any) -> None:
        sep = kwargs.get("sep", " ")
        msg = sep.join(str(arg) for arg in args)
        _append(f"stdout line={msg}")
        if msg.startswith("[SESSION]"):
            _ORIGINAL_PRINT(*args, **kwargs)
            return
        event = _event_from_message(msg)
        if event:
            major(event)

    builtins.print = _filtered_print
    _FILTER_INSTALLED = True


def reset_for_tests() -> None:
    _last_major.clear()
