import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
WWW_MARK = ROOT / "www_mark"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class TestWwwMarkLayoutStructure:
    def test_html_has_grid_layout(self):
        text = _read(WWW_MARK / "index.html")
        assert 'grid-template-columns' in text or 'app-shell' in text

    def test_html_has_top_header(self):
        text = _read(WWW_MARK / "index.html")
        assert 'top-header' in text

    def test_html_has_left_panel(self):
        text = _read(WWW_MARK / "index.html")
        assert 'left-panel' in text

    def test_html_has_center_stage(self):
        text = _read(WWW_MARK / "index.html")
        assert 'center-stage' in text

    def test_html_has_right_panel(self):
        text = _read(WWW_MARK / "index.html")
        assert 'right-panel' in text

    def test_html_has_command_bar(self):
        text = _read(WWW_MARK / "index.html")
        assert 'command-bar' in text

    def test_html_has_settings_overlay(self):
        text = _read(WWW_MARK / "index.html")
        assert 'settings-overlay' in text

    def test_html_has_debug_panel(self):
        text = _read(WWW_MARK / "index.html")
        assert 'debug-panel' in text

    def test_html_has_metric_blocks(self):
        text = _read(WWW_MARK / "index.html")
        assert 'metric-cpu' in text
        assert 'metric-mem' in text

    def test_html_has_nexi_logo_section(self):
        text = _read(WWW_MARK / "index.html")
        assert 'J.A.R.V.I.S' in text

    def test_css_has_grid_layout(self):
        text = _read(WWW_MARK / "style.css")
        assert 'grid-template-columns' in text
        assert 'grid-template-rows' in text

    def test_css_has_panels(self):
        text = _read(WWW_MARK / "style.css")
        assert '.left-panel' in text
        assert '.center-stage' in text
        assert '.right-panel' in text

    def test_css_has_command_bar(self):
        text = _read(WWW_MARK / "style.css")
        assert '.command-bar' in text

    def test_css_has_mark_colors(self):
        text = _read(WWW_MARK / "style.css")
        assert '#00d4ff' in text or '--pri' in text
        assert '#00060a' in text or '--bg' in text