import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]


def test_ui_button_uses_internal_wake():
    main_js = (ROOT / "www" / "main.js").read_text(encoding="utf-8")
    assert "toggleNexiSleepWake" in main_js
    assert "wakeNexiFromUi" in main_js
    assert 'hotkey("win", "j")' not in main_js


def test_typed_chat_uses_command_bus_endpoint():
    main_js = (ROOT / "www" / "main.js").read_text(encoding="utf-8")
    assert "submitUserCommand" in main_js
    assert "eel.allCommands(message)" not in main_js


def test_runtime_bridge_uses_command_bus():
    bridge = (ROOT / "engine" / "runtime_bridge.py").read_text(encoding="utf-8")
    assert "submit_user_command" in bridge
