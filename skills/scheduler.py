"""Reminders & alarms — persisted store + background checker thread."""

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

SCHEDULE_PATH = Path(__file__).resolve().parent.parent / "data" / "schedule.json"

_thread = None
_lock = threading.Lock()


def _load() -> list:
    try:
        if SCHEDULE_PATH.exists():
            return json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save(items: list) -> None:
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _add(item: dict) -> None:
    with _lock:
        items = _load()
        items.append(item)
        _save(items)


def parse_when(text: str):
    """Return (clean_text, due_timestamp) where due may be None if not found."""
    low = text.lower()

    m = re.search(r"\bin\s+(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", low)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = 1 if unit.startswith("sec") else 3600 if unit.startswith("h") else 60
        clean = re.sub(r"\bin\s+\d+\s*\w+", "", text).strip()
        return clean, time.time() + n * mult

    m = re.search(r"\b(?:at|for|by)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", low)
    if m:
        hour, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ap == "pm" and hour < 12:
            hour += 12
        if ap == "am" and hour == 12:
            hour = 0
        now = datetime.now()
        target = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        clean = re.sub(r"\b(?:at|for|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?", "", text).strip()
        return clean, target.timestamp()

    return text.strip(), None


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%I:%M %p").lstrip("0")


def set_reminder(entity: str) -> dict:
    text, due = parse_when(entity)
    if due is None:
        return {"handled": True, "message": "When? Try 'in 10 minutes' or 'at 7 pm'."}
    text = re.sub(r"^(to|that|about)\s+", "", text).strip() or "your reminder"
    _add({"text": text, "due": due, "fired": False, "kind": "Reminder"})
    return {"handled": True, "message": f"Okay, I'll remind you to {text} at {_fmt(due)}."}


def set_alarm(entity: str) -> dict:
    _, due = parse_when(entity)
    if due is None:
        return {"handled": True, "message": "When should the alarm go off? Try 'at 7 am'."}
    _add({"text": "Alarm", "due": due, "fired": False, "kind": "Alarm"})
    return {"handled": True, "message": f"Alarm set for {_fmt(due)}."}


def show_reminders() -> dict:
    pending = [i for i in _load() if not i.get("fired")]
    if not pending:
        return {"handled": True, "message": "You have no reminders."}
    lines = [f"{i['kind']} at {_fmt(i['due'])}: {i['text']}" for i in sorted(pending, key=lambda x: x["due"])]
    return {"handled": True, "message": "Pending:\n" + "\n".join(lines)}


def _fire(item: dict) -> None:
    msg = item["text"] if item["kind"] == "Reminder" else "Alarm"
    try:
        from core.tts import speak
        speak(f"{item['kind']}: {msg}")
    except Exception:
        pass
    try:
        from core.ui_state import safe_eel_call
        safe_eel_call("appendLog", "sys", f"⏰ {item['kind']}: {msg}")
    except Exception:
        pass


def _check_loop(stop_event) -> None:
    while stop_event is None or not stop_event.is_set():
        now = time.time()
        changed = False
        with _lock:
            items = _load()
            for i in items:
                if not i.get("fired") and i.get("due", 0) <= now:
                    _fire(i)
                    i["fired"] = True
                    changed = True
            if changed:
                _save(items)
        time.sleep(20)


def start_scheduler(stop_event=None) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_check_loop, args=(stop_event,), daemon=True)
    _thread.start()
    print("[SCHEDULER] started", flush=True)
