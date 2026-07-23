from __future__ import annotations

import threading

_lock = threading.Lock()
_interrupt = threading.Event()
_speaking = False
_source = ""
_engine = None
_generation = 0


def request_interrupt(source: str, reason: str = "") -> None:
    global _source, _generation
    safe_source = (source or "unknown").strip() or "unknown"
    safe_reason = (reason or "").strip()
    with _lock:
        _source = safe_source
        engine = _engine
        _generation += 1
        _interrupt.set()
    print(f"[INTERRUPT] requested source={safe_source} reason={safe_reason}", flush=True)
    print("[TTS] fade_out_started ms=250", flush=True)
    print("[TTS] stop_requested", flush=True)
    if engine is not None:
        try:
            engine.stop()
            print(f"[TTS] interrupted source={safe_source}", flush=True)
        except Exception as e:
            print(f"[TTS] interrupt_stop_failed reason={type(e).__name__}", flush=True)


def should_interrupt() -> bool:
    return _interrupt.is_set()


def clear_interrupt() -> None:
    global _source
    with _lock:
        _source = ""
        _interrupt.clear()


def is_speaking() -> bool:
    with _lock:
        return _speaking


def set_speaking(value: bool) -> None:
    global _speaking
    with _lock:
        _speaking = bool(value)


def set_tts_engine(engine) -> None:
    global _engine
    with _lock:
        _engine = engine


def get_interrupt_source() -> str:
    with _lock:
        return _source


def get_interrupt_generation() -> int:
    with _lock:
        return _generation
