import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
WWW_MARK = ROOT / "www_mark"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class TestWwwMarkSecurity:
    def test_main_js_uses_ui_submit_text(self):
        text = _read(WWW_MARK / "main.js")
        assert "eel.ui_submit_text" in text, "main.js must use eel.ui_submit_text for commands"

    def test_main_js_no_direct_gemini(self):
        text = _read(WWW_MARK / "main.js")
        assert "eel.gemini" not in text
        assert "eel.groq" not in text

    def test_controller_js_no_api_keys(self):
        text = _read(WWW_MARK / "controller.js")
        assert "api_key" not in text.lower()
        assert "apikey" not in text.lower()

    def test_html_no_inline_api_fields(self):
        text = _read(WWW_MARK / "index.html")
        assert 'api_key' not in text.lower()
        assert 'password' not in text.lower()

    def test_all_js_no_direct_tool_execution(self):
        for js_file in WWW_MARK.glob("*.js"):
            text = _read(js_file)
            assert "tool_registry" not in text.lower()
            assert "local_skills" not in text.lower()
            assert "gemini_brain" not in text.lower()

    def test_js_has_safe_submit_function(self):
        text = _read(WWW_MARK / "main.js")
        assert "function submit" in text
        assert "eel.ui_submit_text" in text