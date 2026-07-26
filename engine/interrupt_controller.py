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


def interrupt_and_wait(source: str, reason: str = "", timeout: float = 2.0) -> bool:
    """Interrupt the speaker and clear only once it has actually stopped.

    Callers used to do request_interrupt() immediately followed by
    clear_interrupt(). The stop is asynchronous, so clearing straight away
    could drop the flag while audio was still winding down - producing
    overlapping TTS, speech that continued past a barge-in, and wake events
    landing during audio decay. Waiting for the producer to report
    is_speaking() == False is that missing acknowledgement.

    Returns True if the speaker stopped within `timeout`.
    """
    import time as _time

    request_interrupt(source=source, reason=reason)
    deadline = _time.monotonic() + max(0.0, timeout)
    while is_speaking() and _time.monotonic() < deadline:
        _time.sleep(0.02)
    stopped = not is_speaking()
    if not stopped:
        print(f"[INTERRUPT] speaker did not stop within {timeout:.1f}s source={source}", flush=True)
    clear_interrupt()
    return stopped


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
