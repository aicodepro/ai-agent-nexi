import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]


def test_ui_button_uses_internal_wake():
    main_js = (ROOT / "www_mark" / "main.js").read_text(encoding="utf-8")
    assert "toggleNexiSleepWake" in main_js
    assert "wakeNexiFromUi" in main_js
    assert 'hotkey("win", "j")' not in main_js


def test_typed_chat_uses_command_bus_endpoint():
    main_js = (ROOT / "www_mark" / "main.js").read_text(encoding="utf-8")
    ui_adapter = (ROOT / "engine" / "ui_adapter.py").read_text(encoding="utf-8")
    # Typed chat calls eel.ui_submit_text, which routes through
    # engine.ui_adapter.submit_text -> engine.command_bus.submit_user_command (the
    # command bus) rather than exposing submitUserCommand directly to JS.
    assert "eel.ui_submit_text" in main_js
    assert "submit_user_command" in ui_adapter
    assert "eel.allCommands(message)" not in main_js


def test_runtime_bridge_uses_command_bus():
    bridge = (ROOT / "engine" / "runtime_bridge.py").read_text(encoding="utf-8")
    assert "submit_user_command" in bridge
