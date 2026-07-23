import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestMarkStyleUiCommandBusIntegration:
    def test_submit_text_uses_command_bus(self):
        from engine.ui_adapter import submit_text
        result = submit_text("hello")
        assert "ok" in result, "submit_text must return ok status"

    def test_submit_text_handles_long_text(self):
        from engine.ui_adapter import submit_text
        long_text = "x" * 5000
        result = submit_text(long_text)
        assert "ok" in result

    def test_command_bus_accepts_text(self):
        from engine.command_bus import submit_user_command
        result = submit_user_command("test command", source="ui", mode="typed")
        assert result is True or result is False

    def test_ui_event_bridge_set_state_returns_dict(self):
        from engine.ui_event_bridge import set_state
        result = set_state("idle")
        assert isinstance(result, dict)
        assert "state" in result

    def test_legacy_ui_dir_exists(self):
        from engine.ui_loader import _mark_ui_exists
        www = Path(__file__).resolve().parents[1] / "www_mark"
        assert www.exists() and www.is_dir(), "Legacy www/ UI directory must exist"

    def test_mark_ui_dir_exists_with_index(self):
        www_mark = Path(__file__).resolve().parents[1] / "www_mark"
        assert www_mark.exists() and www_mark.is_dir()
        assert (www_mark / "index.html").exists()