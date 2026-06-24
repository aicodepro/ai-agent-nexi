from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mark_ui_dashboard_markup_present():
    html = (ROOT / "www_mark" / "index.html").read_text(encoding="utf-8")
    assert "diagnostics-dashboard" in html
    assert "dashboard-panels" in html


def test_mark_ui_dashboard_controller_present():
    controller = (ROOT / "www_mark" / "controller.js").read_text(encoding="utf-8")
    assert "updateDashboard" in controller
    assert "diagnosticsResult" in controller
    assert "getDashboardState" in controller
    assert "tone-focused" in controller


def test_mark_ui_dashboard_styles_present():
    css = (ROOT / "www_mark" / "style.css").read_text(encoding="utf-8")
    assert ".monitor-dashboard" in css
    assert "body.tone-focused" in css
