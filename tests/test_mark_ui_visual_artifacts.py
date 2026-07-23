import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "ui_mark_validation"
WWW_MARK = ROOT / "www_mark"


class TestMarkUiVisualArtifacts:
    def test_artifacts_dir_exists(self):
        assert ARTIFACTS.exists(), "artifacts/ui_mark_validation missing"

    def test_index_html_valid(self):
        text = (WWW_MARK / "index.html").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in text
        assert "</html>" in text

    def test_css_valid(self):
        text = (WWW_MARK / "style.css").read_text(encoding="utf-8")
        assert ":root" in text
        assert "{" in text

    def test_logo_file_exists(self):
        path = WWW_MARK / "assets" / "nexi-logo.svg"
        assert path.exists(), "nexi-logo.svg missing"
        assert path.stat().st_size > 50, "nexi-logo.svg too small"

    def test_hud_js_valid(self):
        text = (WWW_MARK / "hud_orb.js").read_text(encoding="utf-8")
        assert "requestAnimationFrame" in text
        assert "canvas" in text.lower()

    def test_main_js_valid(self):
        text = (WWW_MARK / "main.js").read_text(encoding="utf-8")
        assert "submit" in text.lower()
        assert "eel" in text

    def test_controller_js_valid(self):
        text = (WWW_MARK / "controller.js").read_text(encoding="utf-8")
        assert "updateNexiState" in text
        assert "senderText" in text

    # Binary assets are not text and never will be. The list was images-only until
    # the HUD gained media/hud_bg.mp4 + dna.mp4, which failed this as "not UTF-8".
    # Exempt by category so the next asset type added doesn't re-break it.
    BINARY_SUFFIXES = {
        ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif",
        ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg",
        ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pdf", ".zip",
    }

    def test_all_files_utf8(self):
        checked = 0
        for f in WWW_MARK.glob("**/*"):
            if not f.is_file() or f.suffix.lower() in self.BINARY_SUFFIXES:
                continue
            try:
                f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                assert False, f"{f.name} is not valid UTF-8"
            checked += 1
        # guard against the skip list quietly growing until this tests nothing
        assert checked >= 5, f"only {checked} text files checked — skip list too broad?"