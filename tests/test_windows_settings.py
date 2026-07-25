import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.tool_registry import get_tool, execute_tool
from engine.groq_intent_router_v2 import _deterministic_router
from engine import intent_taxonomy as tax
from engine import windows_settings as ws


SETTINGS_TOOLS = [
    "open_settings", "open_wifi_settings", "open_bluetooth_settings",
    "open_display_settings", "open_sound_settings", "open_microphone_settings",
    "open_camera_settings", "open_startup_settings", "open_windows_update",
    "open_settings_page",
]


def _route(phrase):
    return _deterministic_router(phrase, {}).get("intent")


@pytest.fixture
def captured_uris(monkeypatch):
    """Capture launches so tests never actually open Settings windows."""
    calls = []
    monkeypatch.setattr(ws, "_open_uri", lambda uri: calls.append(uri) or True)
    return calls


def test_settings_tools_registered():
    for name in SETTINGS_TOOLS:
        assert get_tool(name) is not None, f"{name} not registered"


def test_settings_tools_whitelisted():
    for name in SETTINGS_TOOLS:
        assert name in tax.ALLOWED_INTENTS, f"{name} missing from ALLOWED_INTENTS"
        assert name in tax.TOOL_INTENTS, f"{name} missing from TOOL_INTENTS"


def test_settings_uri_mapping():
    assert ws.settings_uri("wifi") == "ms-settings:network-wifi"
    assert ws.settings_uri("bluetooth") == "ms-settings:bluetooth"
    assert ws.settings_uri("display") == "ms-settings:display"
    assert ws.settings_uri("microphone") == "ms-settings:privacy-microphone"
    assert ws.settings_uri("camera") == "ms-settings:privacy-webcam"
    assert ws.settings_uri("startup") == "ms-settings:startupapps"
    assert ws.settings_uri("windows update") == "ms-settings:windowsupdate"
    assert ws.settings_uri("home") == "ms-settings:"
    assert ws.settings_uri("totally unknown page xyz") == ""


def test_open_wifi_settings_executes_and_verifies(captured_uris):
    r = execute_tool("open_wifi_settings", {})
    assert r["success"] is True and r["verified"] is True
    assert r["tool"] == "open_wifi_settings"
    assert r.get("uri") == "ms-settings:network-wifi"
    assert captured_uris == ["ms-settings:network-wifi"]


def test_open_settings_page_with_slot(captured_uris):
    r = execute_tool("open_settings_page", {"page": "bluetooth"})
    assert r["success"] is True and r["verified"] is True
    assert r.get("uri") == "ms-settings:bluetooth"
    assert captured_uris == ["ms-settings:bluetooth"]


def test_open_settings_page_unknown_does_not_fake_success(captured_uris):
    r = execute_tool("open_settings_page", {"page": "nonexistent zzz"})
    assert r.get("verified") is not True
    assert captured_uris == []


def test_launch_failure_is_not_verified(monkeypatch):
    def boom(uri):
        raise OSError("no shell")
    monkeypatch.setattr(ws, "_open_uri", boom)
    r = execute_tool("open_display_settings", {})
    assert r.get("verified") is not True


def test_routing_open_prefixed_settings():
    assert _route("open wifi settings") == "open_wifi_settings"
    assert _route("open bluetooth settings") == "open_bluetooth_settings"
    assert _route("open display settings") == "open_display_settings"
    assert _route("open camera settings") == "open_camera_settings"
    assert _route("open microphone settings") == "open_microphone_settings"
    assert _route("open windows settings") == "open_settings"


def test_routing_bare_settings_phrases():
    assert _route("bluetooth settings") == "open_bluetooth_settings"
    assert _route("sound settings") == "open_sound_settings"
    assert _route("startup apps") == "open_startup_settings"
    assert _route("windows update") == "open_windows_update"
