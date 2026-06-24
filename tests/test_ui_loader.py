import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]


class TestUiLoader:
    def test_get_ui_mode_default(self):
        os.environ.pop("JARVIS_UI_MODE", None)
        from engine.ui_loader import get_ui_mode
        mode = get_ui_mode()
        assert mode in {"legacy", "mark"}

    def test_get_ui_mode_legacy(self):
        os.environ["JARVIS_UI_MODE"] = "legacy"
        from engine import ui_loader
        import importlib
        importlib.reload(ui_loader)
        assert ui_loader.get_ui_mode() == "legacy"

    def test_get_ui_mode_mark(self):
        os.environ["JARVIS_UI_MODE"] = "mark"
        from engine import ui_loader
        import importlib
        importlib.reload(ui_loader)
        assert ui_loader.get_ui_mode() == "mark"

    def test_get_ui_mode_invalid_falls_back(self):
        os.environ["JARVIS_UI_MODE"] = "bogus"
        from engine import ui_loader
        import importlib
        importlib.reload(ui_loader)
        assert ui_loader.get_ui_mode() == "legacy"

    def test_get_ui_dir_legacy(self):
        os.environ["JARVIS_UI_MODE"] = "legacy"
        from engine import ui_loader
        import importlib
        importlib.reload(ui_loader)
        d = ui_loader.get_ui_dir()
        assert "www" in d or "legacy" in str(d).lower()

    def test_mark_ui_exists(self):
        from engine.ui_loader import _mark_ui_exists
        assert _mark_ui_exists() is True, "www_mark should exist with index.html"