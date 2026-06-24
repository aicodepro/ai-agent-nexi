import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ui_state_manager import UIStateManager


def test_dedupe_same_state():
    manager = UIStateManager(dedupe_ms=200)
    e1 = manager.emit("thinking", source="system", force=True)
    e2 = manager.emit("thinking", source="system")
    assert e1 is not None
    assert e2 is None


def test_dedupe_different_source_allows():
    manager = UIStateManager(dedupe_ms=200)
    e1 = manager.emit("thinking", source="hotword", force=True)
    e2 = manager.emit("thinking", source="system", force=True)
    assert e1 is not None
    assert e2 is not None


def test_no_duplicate_wake_event():
    manager = UIStateManager(dedupe_ms=200)
    e1 = manager.emit("wake_detected", source="hotword", force=True)
    e2 = manager.emit("wake_detected", source="hotword")
    assert e1 is not None
    assert e2 is None


def test_different_states_no_dedupe():
    manager = UIStateManager(dedupe_ms=200)
    e1 = manager.emit("listening", source="system", force=True)
    e2 = manager.emit("thinking", source="system", force=True)
    assert e1 is not None
    assert e2 is not None


def test_force_bypasses_dedupe():
    manager = UIStateManager(dedupe_ms=5000)
    e1 = manager.emit("sleep", source="system", force=True)
    e2 = manager.emit("sleep", source="system", force=True)
    assert e1 is not None
    assert e2 is not None
