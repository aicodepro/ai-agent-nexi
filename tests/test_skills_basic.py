"""Basic skill tests against the modules that actually implement them.

This file used to import `skills.apps` / `skills.web` / `skills.files` / `skills.system` —
empty leftover packages from the refactor into `engine/` (see tests/test_imports.py). All
16 tests failed with ModuleNotFoundError on every run, so none of them ever checked
anything.

Two things changed with the move, and the tests are written against the NEW contract:

1. Skills return `{"success": bool, "message": str, "tool": str}`, not `{"handled": True}`.
2. `_safe_name` REJECTS a name containing invalid characters (returns None) instead of
   silently stripping them. Rejecting is the safer contract for something fed by ASR text
   — a stripped name still creates a file, just not the one anyone asked for.

The single-purpose skills (time, clipboard) are now tool_registry handlers reached through
`execute_tool`, so they are tested through that dispatch — the same path NEXI uses.
"""
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch):
    """Neutralize everything these skills can do to the real machine.

    pyautogui matters most: `_open_app` falls back to press("win") / write(name) /
    press("enter") for any app not in APP_COMMANDS. Unmocked, that types into whatever
    window has focus — the test run would drive the developer's actual desktop.
    """
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: None)

    fake_gui = types.ModuleType("pyautogui")
    fake_gui.calls = []
    fake_gui.press = lambda key: fake_gui.calls.append(("press", key))
    fake_gui.write = lambda text, **kw: fake_gui.calls.append(("write", text))
    monkeypatch.setitem(sys.modules, "pyautogui", fake_gui)

    # _open_app polls psutil for up to 2s waiting for the process to appear. Report a
    # match so the known-app path returns immediately instead of burning the timeout.
    fake_psutil = types.ModuleType("psutil")
    fake_psutil.process_iter = lambda attrs=None: [
        types.SimpleNamespace(info={"name": "chrome.exe"})
    ]
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    return types.SimpleNamespace(urls=opened, gui=fake_gui)


class TestApps:
    def test_open_known_app_reports_success(self):
        from engine.local_skills import open_app
        result = open_app("chrome")
        assert result["success"] is True
        assert result["tool"] == "open_app"
        assert result["app"] == "chrome"

    def test_open_known_app_claims_no_verification(self):
        """The launch is fire-and-forget, so open_app must NOT set verified=True —
        tool_result_verifier confirms a real process instead of trusting the claim."""
        from engine.local_skills import open_app
        assert "verified" not in open_app("chrome")

    def test_unknown_app_falls_back_to_start_menu(self, no_real_side_effects):
        from engine.local_skills import open_app
        result = open_app("nonexistent12345")
        assert result["success"] is True
        assert ("write", "nonexistent12345") in no_real_side_effects.gui.calls

    def test_app_commands_has_common_apps(self):
        from engine.local_skills import APP_COMMANDS
        for app in ("chrome", "notepad", "calculator", "vs code"):
            assert app in APP_COMMANDS


class TestWeb:
    def test_open_known_site_uses_mapped_url(self, no_real_side_effects):
        from engine.local_skills import open_website
        result = open_website("youtube")
        assert result["success"] is True
        assert no_real_side_effects.urls == ["https://www.youtube.com"]

    def test_unknown_site_gets_https_prefix(self, no_real_side_effects):
        from engine.local_skills import open_website
        open_website("example.com")
        assert no_real_side_effects.urls == ["https://example.com"]

    def test_web_search_delegates_to_live_search(self, no_real_side_effects):
        # web_search no longer opens a Google URL; it delegates to the live
        # intelligence engine. Mocked so the test stays offline/deterministic.
        from unittest.mock import patch
        from engine.local_skills import web_search
        with patch("engine.live_intelligence.live_web_search") as mock_search:
            mock_search.return_value = {"success": True, "message": "live results"}
            result = web_search("python testing")
        assert result["success"] is True
        mock_search.assert_called_once_with("python testing", mode="search")

    def test_sites_contains_common(self):
        from engine.local_skills import SITES
        for site in ("youtube", "gmail", "github"):
            assert site in SITES


class TestFiles:
    def test_safe_name_rejects_invalid_characters(self):
        """Rejects rather than strips — see module docstring."""
        from engine.local_skills import _safe_name
        assert _safe_name('file<>:"/|?*name') is None

    def test_safe_name_rejects_traversal(self):
        from engine.local_skills import _safe_name
        for evil in ("..", ".", "../etc/passwd", "notes/../../secret"):
            assert _safe_name(evil) is None, f"{evil!r} must not be accepted"

    def test_safe_name_accepts_and_caps_ordinary_names(self):
        from engine.local_skills import _safe_name
        assert _safe_name("  my notes.txt  ") == "my notes.txt"
        assert len(_safe_name("a" * 500)) == 160

    def test_resolve_location_desktop(self):
        from engine.local_skills import resolve_location
        assert str(resolve_location("desktop")).endswith("Desktop")

    def test_resolve_location_documents(self):
        from engine.local_skills import resolve_location
        assert str(resolve_location("documents")).endswith("Documents")

    def test_resolve_location_rejects_unknown(self):
        from engine.local_skills import resolve_location
        assert resolve_location("somewhere on the moon") is None


class TestSystemTools:
    """time / clipboard are tool_registry handlers, dispatched via execute_tool."""

    @pytest.fixture(autouse=True)
    def _disable_llm_safety_gate(self, monkeypatch):
        """clipboard_read/clipboard_write_safe are medium/high risk, so the LLM safety gate
        blocks them when offline (no GROQ_API_KEY) before the handler runs."""
        monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")

    def test_tell_time(self):
        from engine.tool_registry import execute_tool
        result = execute_tool("tell_time")
        assert result["success"] is True
        assert result["message"]

    def test_clipboard_read(self, monkeypatch):
        fake_clip = types.ModuleType("pyperclip")
        fake_clip.paste = lambda: "clipboard content"
        fake_clip.copy = lambda t: None
        monkeypatch.setitem(sys.modules, "pyperclip", fake_clip)

        from engine.tool_registry import execute_tool
        result = execute_tool("clipboard_read")
        assert result["success"] is True
        assert "clipboard content" in result["message"]

    def test_clipboard_write(self, monkeypatch):
        written = []
        fake_clip = types.ModuleType("pyperclip")
        fake_clip.paste = lambda: ""
        fake_clip.copy = written.append
        monkeypatch.setitem(sys.modules, "pyperclip", fake_clip)

        from engine.tool_registry import execute_tool
        result = execute_tool("clipboard_write_safe", {"text": "test"}, confirmed=True)
        assert result["success"] is True
        assert written == ["test"]

    def test_clipboard_write_requires_confirmation(self, monkeypatch):
        """safety=high + confirm=True: writing the clipboard must not happen off an
        unconfirmed model call. Approval comes only from the `confirmed=` kwarg, which
        the model cannot set via a slot."""
        written = []
        fake_clip = types.ModuleType("pyperclip")
        fake_clip.copy = written.append
        monkeypatch.setitem(sys.modules, "pyperclip", fake_clip)

        from engine.tool_registry import execute_tool
        result = execute_tool("clipboard_write_safe", {"text": "test"})
        assert result["success"] is False
        assert result["requires_confirmation"] is True
        assert written == []

    def test_model_cannot_self_confirm_via_slot(self):
        """A model emitting confirmed=True as a slot must not satisfy the gate."""
        from engine.tool_registry import execute_tool
        result = execute_tool("clipboard_write_safe", {"text": "x", "confirmed": True})
        assert result["success"] is False
        assert result["requires_confirmation"] is True

    def test_clipboard_write_asks_when_text_missing(self):
        from engine.tool_registry import execute_tool
        result = execute_tool("clipboard_write_safe", {})
        assert result["success"] is False
        assert result["expects_user_reply"] is True
