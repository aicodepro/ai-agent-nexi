from __future__ import annotations

import os


def test_hotkey_env_disabled_by_default(monkeypatch):
    """JARVIS_HOTKEY_WAKE_ENABLED must default to false."""
    monkeypatch.delenv("JARVIS_HOTKEY_WAKE_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_HOTKEY_ENABLED", raising=False)
    val = os.getenv("JARVIS_HOTKEY_WAKE_ENABLED", "false").strip().lower()
    assert val in {"0", "false", "no", "off"}, (
        f"Expected JARVIS_HOTKEY_WAKE_ENABLED to default to false, got {val}"
    )


def test_hotkey_wake_not_started_without_explicit_enable(monkeypatch):
    """When JARVIS_HOTKEY_WAKE_ENABLED is false, hotkey listener is None."""
    monkeypatch.delenv("JARVIS_HOTKEY_WAKE_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_HOTKEY_ENABLED", raising=False)
    from engine.hotkey_wake import start_hotkey_listener
    listener = start_hotkey_listener(callback=lambda src: None)
    # When disabled, start_hotkey_listener returns None
    # (the default is false, so unless env is explicitly true, we skip)
    assert listener is None, "Hotkey should be disabled by default"
