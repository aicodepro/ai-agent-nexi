import os
import sys
import json
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import UIStateManager, canonical_state


def test_command_fallback_sleep():
    manager = UIStateManager(dedupe_ms=0)
    event = manager.emit("sleep", source="system", status="command_fallback", force=True)
    assert event.state == "sleep"


def test_error_state_after_fallback():
    manager = UIStateManager(dedupe_ms=0)
    event = manager.emit("error", source="system", text="command_failed", force=True)
    assert event.state == "error"
    assert event.text == "command_failed"
