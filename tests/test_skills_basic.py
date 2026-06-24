import pytest


@pytest.fixture(autouse=True)
def mock_subprocess(monkeypatch):
    import subprocess
    def mock_popen(*args, **kwargs):
        class FakeProc:
            def __init__(self):
                self.returncode = 0
            def communicate(self):
                return (b"", b"")
            def poll(self):
                return 0
            def wait(self, timeout=None):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
        return FakeProc()
    def mock_run(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = b""
            stderr = b""
        return FakeResult()
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    monkeypatch.setattr(subprocess, "run", mock_run)


class TestSkillsApps:

    def test_open_chrome(self, mock_subprocess):
        from skills.apps import open_app
        result = open_app("chrome")
        assert isinstance(result, dict)
        assert result.get("handled") is True

    def test_open_unknown(self, mock_subprocess):
        from skills.apps import open_app
        result = open_app("nonexistent12345")
        assert isinstance(result, dict)
        assert result.get("handled") is not False

    def test_close_known(self, mock_subprocess):
        from skills.apps import close_app
        result = close_app("chrome")
        assert isinstance(result, dict)

    def test_close_unknown(self, mock_subprocess):
        from skills.apps import close_app
        result = close_app("nonexistent12345")
        assert isinstance(result, dict)

    def test_app_map_has_common(self):
        from skills.apps import APP_MAP
        assert "chrome" in APP_MAP
        assert "notepad" in APP_MAP
        assert "calculator" in APP_MAP
        assert "vs code" in APP_MAP


class TestSkillsWeb:

    def test_open_website_known(self, monkeypatch):
        monkeypatch.setattr("webbrowser.open", lambda url: True)
        from skills.web import open_website
        result = open_website("google")
        assert isinstance(result, dict)
        assert result.get("handled") is True

    def test_open_website_unknown(self, monkeypatch):
        monkeypatch.setattr("webbrowser.open", lambda url: True)
        from skills.web import open_website
        result = open_website("some_unknown_site_xyz")
        assert isinstance(result, dict)
        assert result.get("handled") is False

    def test_web_search(self, monkeypatch):
        monkeypatch.setattr("webbrowser.open", lambda url: True)
        from skills.web import web_search
        result = web_search("python testing")
        assert result.get("handled") is True

    def test_sites_contains_common(self):
        from skills.web import SITES
        assert "google" in SITES
        assert "youtube" in SITES
        assert "github" in SITES


class TestSkillsFiles:

    def test_safe_name_strips_invalid(self):
        from skills.files import _safe_name
        result = _safe_name('file<>:"/|?*name')
        assert result == "filename"

    def test_resolve_location_desktop(self):
        from skills.files import resolve_location
        path = resolve_location("desktop")
        assert str(path).endswith("Desktop")

    def test_resolve_location_documents(self):
        from skills.files import resolve_location
        path = resolve_location("documents")
        assert str(path).endswith("Documents")


class TestSkillsSystem:

    def test_get_time(self):
        from skills.system import get_time
        result = get_time()
        assert isinstance(result, dict)
        assert result.get("handled") is True
        assert "It's" in result["message"]

    def test_get_weather_no_city(self, monkeypatch):
        import sys
        import types
        fake_requests = types.ModuleType("requests")
        class FakeResp:
            def json(self):
                return {"current_weather": {"temperature": 22, "weathercode": 0}}
            def raise_for_status(self):
                pass
        fake_requests.get = lambda url, **kw: FakeResp()
        monkeypatch.setitem(sys.modules, "requests", fake_requests)
        from skills.system import get_weather
        result = get_weather("")
        assert isinstance(result, dict)
        assert result.get("handled") is True

    def test_read_clipboard_returns_dict(self, monkeypatch):
        import sys
        import types
        fake_clip = types.ModuleType("pyperclip")
        fake_clip.paste = lambda: "clipboard content"
        fake_clip.copy = lambda t: None
        monkeypatch.setitem(sys.modules, "pyperclip", fake_clip)
        from skills.system import read_clipboard
        result = read_clipboard()
        assert isinstance(result, dict)

    def test_copy_to_clipboard(self, monkeypatch):
        import sys
        import types
        fake_clip = types.ModuleType("pyperclip")
        fake_clip.paste = lambda: ""
        fake_clip.copy = lambda t: None
        monkeypatch.setitem(sys.modules, "pyperclip", fake_clip)
        from skills.system import copy_to_clipboard
        result = copy_to_clipboard("test")
        assert isinstance(result, dict)
