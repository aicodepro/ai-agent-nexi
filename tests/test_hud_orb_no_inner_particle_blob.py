import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
WWW_MARK = ROOT / "www_mark"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class TestHudOrbNoInnerBlob:
    def test_orb_js_has_clean_ring_code(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert 'rFace' in text or 'ring' in text.lower()

    def test_orb_js_loads_logo_image(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert 'logo' in text.lower()

    def test_orb_js_has_ring_drawing(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert 'ctx.arc' in text
        assert 'tick' in text.lower() or 'stroke' in text.lower()

    def test_orb_js_has_crosshair(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert 'crosshair' in text.lower() or 'chR' in text

    def test_orb_js_has_state_methods(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert 'setOrbState' in text
        assert 'function step' in text or 'function draw' in text

    def test_orb_js_has_no_blob_drawing(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert 'blur' not in text.lower()
        assert 'shadowBlur' not in text

    def test_orb_js_has_logo_text(self):
        text = _read(WWW_MARK / "hud_orb.js")
        assert "N.E.X.I" in text

    def test_logo_svg_exists(self):
        assert (WWW_MARK / "assets" / "nexi-logo.svg").exists()