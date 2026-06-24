import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
WWW_MARK = ROOT / "www_mark"


class TestWwwMarkUiFiles:
    def test_index_html_exists(self):
        assert (WWW_MARK / "index.html").exists(), "www_mark/index.html missing"

    def test_style_css_exists(self):
        assert (WWW_MARK / "style.css").exists(), "www_mark/style.css missing"

    def test_main_js_exists(self):
        assert (WWW_MARK / "main.js").exists(), "www_mark/main.js missing"

    def test_controller_js_exists(self):
        assert (WWW_MARK / "controller.js").exists(), "www_mark/controller.js missing"

    def test_hud_orb_js_exists(self):
        assert (WWW_MARK / "hud_orb.js").exists(), "www_mark/hud_orb.js missing"

    def test_css_has_dark_theme(self):
        text = (WWW_MARK / "style.css").read_text(encoding="utf-8")
        assert "--bg" in text, "Missing --bg CSS variable"
        assert "--pri" in text, "Missing --pri CSS variable"

    def test_html_has_hud_canvas(self):
        text = (WWW_MARK / "index.html").read_text(encoding="utf-8")
        assert "hud-canvas" in text, "index.html missing hud-canvas element"

    def test_html_has_file_drop_zone(self):
        text = (WWW_MARK / "index.html").read_text(encoding="utf-8")
        assert "file-drop-zone" in text, "index.html missing file-drop-zone"

    def test_orb_js_has_states(self):
        text = (WWW_MARK / "hud_orb.js").read_text(encoding="utf-8")
        required_states = ["idle", "listening", "thinking", "speaking", "error", "sleeping"]
        for s in required_states:
            assert s in text.lower(), f"hud_orb.js missing state: {s}"