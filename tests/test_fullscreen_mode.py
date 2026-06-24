import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_fullscreen_env_defaults_true(monkeypatch):
    monkeypatch.delenv("NEXI_FULLSCREEN", raising=False)
    import engine.ui_loader as ui_loader
    importlib.reload(ui_loader)
    assert ui_loader.should_open_fullscreen() is True
    assert ui_loader.get_window_mode() == "fullscreen"


def test_window_mode_maximized(monkeypatch):
    monkeypatch.setenv("NEXI_FULLSCREEN", "false")
    monkeypatch.setenv("NEXI_WINDOW_MODE", "maximized")
    import engine.ui_loader as ui_loader
    importlib.reload(ui_loader)
    assert ui_loader.get_window_mode() == "maximized"
    assert "--start-maximized" in ui_loader.edge_window_args()


def test_main_logs_fullscreen_request():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "[UI] fullscreen=" in text
    assert "[UI] window_mode=" in text
