import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestUiAdapter:
    def test_submit_empty_text(self):
        from engine.ui_adapter import submit_text
        result = submit_text("")
        assert result["ok"] is False
        assert "empty" in result.get("error", "")

    def test_submit_whitespace_only(self):
        from engine.ui_adapter import submit_text
        result = submit_text("   ")
        assert result["ok"] is False

    def test_submit_null(self):
        from engine.ui_adapter import submit_text
        result = submit_text(None)
        assert result["ok"] is False

    def test_file_drop_empty(self):
        from engine.ui_adapter import submit_file_drop
        result = submit_file_drop([])
        assert result["ok"] is False

    def test_file_drop_null(self):
        from engine.ui_adapter import submit_file_drop
        result = submit_file_drop(None)
        assert result["ok"] is False

    def test_get_env_status_returns_bools(self):
        from engine.ui_adapter import get_env_status
        status = get_env_status()
        assert isinstance(status, dict)
        assert all(isinstance(v, bool) for v in status.values())

    def test_get_env_status_has_keys(self):
        from engine.ui_adapter import get_env_status
        status = get_env_status()
        assert "groq" in status
        assert "gemini" in status

    def test_get_ui_capabilities(self):
        from engine.ui_adapter import get_ui_capabilities
        caps = get_ui_capabilities()
        assert isinstance(caps, dict)
        assert all(isinstance(v, bool) for v in caps.values())

    def test_no_api_values_in_status(self):
        from engine.ui_adapter import get_env_status
        status = get_env_status()
        for key, val in status.items():
            assert val is True or val is False, f"Value for {key} is {val}, expected bool"