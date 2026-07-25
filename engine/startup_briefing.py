"""Two-phase startup (Mark-48 idea, native to NEXI).

Phase 1: greet immediately. Phase 2: news is fetched *concurrently* in the
background (not sequentially), and — only if NEXI_STARTUP_BRIEFING is enabled —
a one-line headline is spoken once it arrives. Session state is reset first so a
fresh session starts clean.
"""
import os
import threading
import time


def _briefing_enabled():
    return os.getenv("NEXI_STARTUP_BRIEFING", "").strip().lower() in ("1", "true", "yes")


def two_phase_startup(greet=None, speak=None):
    """greet(): short phase-1 greeting (may be None). speak(text): TTS for phase 2."""
    try:
        from engine.session_reset import reset_session
        reset_session()
    except Exception:
        pass

    news = None
    try:
        from engine import news as news
        news.prefetch_news()  # phase-2 producer starts loading concurrently
    except Exception:
        news = None

    # Phase 1 — greet now; news keeps loading in the background.
    if greet:
        try:
            greet()
        except Exception:
            pass

    # Phase 2 — deliver a headline once ready, only if enabled and we can speak.
    if news and speak and _briefing_enabled():
        def _deliver():
            for _ in range(20):  # up to ~4s
                arts = news.cached_news()
                if arts:
                    try:
                        speak(f"Top headline: {arts[0]['title']}")
                    except Exception:
                        pass
                    return
                time.sleep(0.2)

        threading.Thread(target=_deliver, daemon=True).start()
