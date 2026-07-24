"""
Post-TTS cleanup and audio buffer flushing.

Implements post-speech cooldown functionality to:
- Provide consistent cooldown period after TTS
- Flush audio buffers to prevent audio overlap
- Prevent accidental re-listening during cooldown
- Ensure clean state transitions

Usage:
    from engine.post_tts_cleanup import (
        post_tts_cleanup,
        flush_audio_buffers,
        is_in_cooldown,
    )
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

# Configuration constants
DEFAULT_COOLDOWN_MS = 800
DEFAULT_BUFFER_FLUSH_TIMEOUT_MS = 500

# Global state
_cooldown_lock = threading.Lock()
_cooldown_active = False
_cooldown_start_time = 0.0
_cooldown_end_time = 0.0
_audio_buffers_flushed = False
_cooldown_callbacks: list[Callable[[], None]] = []


def post_tts_cleanup(*, on_complete: Callable[[], None] | None = None) -> bool:
    """Execute post-TTS cleanup and enter cooldown.

    Returns:
        True if cleanup was successful, False if already in cooldown
    """
    global _cooldown_active, _cooldown_start_time, _cooldown_end_time, _audio_buffers_flushed

    current_time = time.time()

    # Start cooldown
    with _cooldown_lock:
        if on_complete is not None:
            _cooldown_callbacks.append(on_complete)
        if _cooldown_active and current_time < _cooldown_end_time:
            remaining_ms = int((_cooldown_end_time - current_time) * 1000.0)
            print(f"[POST_TTS] cooldown_active reason=still_in_cooldown remaining_ms={remaining_ms}", flush=True)
            return False

        _cooldown_active = True
        _cooldown_start_time = current_time
        _cooldown_end_time = current_time + (DEFAULT_COOLDOWN_MS / 1000.0)
        _audio_buffers_flushed = False

    # Flush audio buffers
    flush_audio_buffers()

    # Start cooldown cleanup thread
    threading.Thread(
        target=_cooldown_cleanup,
        daemon=True,
        name="post-tts-cooldown",
    ).start()

    print(f"[POST_TTS] cooldown_started ms={DEFAULT_COOLDOWN_MS}", flush=True)
    return True


def flush_audio_buffers() -> None:
    """Flush all audio buffers to prevent overlap."""
    global _audio_buffers_flushed

    if _audio_buffers_flushed:
        return

    try:
        # Stop all active audio sources
        _stop_tts_engine()
        _stop_audio_stream()
        _clear_audio_cache()
        _interrupt_active_sounds()

        _audio_buffers_flushed = True
        print(f"[AUDIO_BUFFER] flushed_all_buffers", flush=True)

    except Exception as e:
        print(f"[AUDIO_BUFFER] flush_failed reason={type(e).__name__}: {e}", flush=True)


def is_in_cooldown() -> bool:
    """Check if we're in cooldown period.

    Returns:
        True if in cooldown
    """
    current_time = time.time()
    return _cooldown_active and current_time < _cooldown_end_time


def get_cooldown_remaining_ms() -> int:
    """Get remaining cooldown time in milliseconds.

    Returns:
        Remaining time in milliseconds, or 0 if not in cooldown
    """
    current_time = time.time()
    if not _cooldown_active or current_time >= _cooldown_end_time:
        return 0

    return int((_cooldown_end_time - current_time) * 1000.0)


def reset_cooldown() -> None:
    """Reset cooldown state (use with caution)."""
    global _cooldown_active, _cooldown_start_time, _cooldown_end_time

    with _cooldown_lock:
        _cooldown_active = False
        _cooldown_start_time = 0.0
        _cooldown_end_time = 0.0
        _cooldown_callbacks.clear()

    print(f"[POST_TTS] cooldown_reset", flush=True)


def _stop_tts_engine() -> None:
    """Stop the TTS engine if active."""
    try:
        from engine.interrupt_controller import set_speaking, clear_interrupt

        set_speaking(False)
        clear_interrupt()
    except Exception:
        pass


def _stop_audio_stream() -> None:
    """Stop any active audio stream."""
    try:
        from engine.tts_provider_manager import stop_audio_stream

        stop_audio_stream()
    except Exception:
        pass


def _clear_audio_cache() -> None:
    """Clear audio cache."""
    try:
        from engine.audio_cache import clear_cache

        clear_cache()
    except Exception:
        pass


def _interrupt_active_sounds() -> None:
    """Interrupt any active sounds."""
    try:
        import pygame

        pygame.mixer.music.stop()
        pygame.mixer.stop()
    except Exception:
        pass


def _cooldown_cleanup() -> None:
    """Background cleanup task for cooldown."""
    global _cooldown_active, _cooldown_start_time, _cooldown_end_time
    current_time = time.time()
    sleep_duration = 0.1  # Check every 100ms

    while _cooldown_active and current_time < _cooldown_end_time:
        time.sleep(sleep_duration)
        current_time = time.time()

    # Cooldown complete
    if _cooldown_active and current_time >= _cooldown_end_time:
        callbacks: list[Callable[[], None]] = []
        with _cooldown_lock:
            if _cooldown_active:
                _cooldown_active = False
                _cooldown_start_time = 0.0
                _cooldown_end_time = 0.0
                callbacks = list(_cooldown_callbacks)
                _cooldown_callbacks.clear()

        print(f"[POST_TTS] cooldown_complete", flush=True)
        for callback in callbacks:
            try:
                callback()
            except Exception:
                pass


# Convenience functions for integration

def setup_post_tts_integration() -> None:
    """Set up integration with TTS provider manager."""
    try:
        from engine.tts_provider_manager import register_post_tts_callback

        register_post_tts_callback(post_tts_cleanup)
    except ImportError:
        pass


def setup_post_tts_in_command_bus() -> None:
    """Set up integration with command bus."""
    try:
        from engine.command_bus import can_accept_full_command

        # This is handled in command_bus.py via voice_state_machine
        pass
    except ImportError:
        pass
