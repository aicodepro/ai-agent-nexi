import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]


def test_startup_animation_classes_exist():
    index = (ROOT / "www_mark" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "www_mark" / "style.css").read_text(encoding="utf-8")
    controller = (ROOT / "www_mark" / "controller.js").read_text(encoding="utf-8")
    assert "Nexi" in index
    assert "nexi" in controller.lower()
    assert "style.css" in index


def test_state_animation_selectors_exist():
    css = (ROOT / "www_mark" / "style.css").read_text(encoding="utf-8")
    orb_js = (ROOT / "www_mark" / "hud_orb.js").read_text(encoding="utf-8")
    assert ".nexi-state" in css
    # No @keyframes: the state animation is a requestAnimationFrame canvas draw loop in
    # hud_orb.js, not CSS keyframes (CSS keyframes/DOM rebuilds were the measured cause of
    # UI lag and were deliberately removed; see nexi-ui-lag-domthrash memory note).
    assert "requestAnimationFrame" in orb_js
    assert "waveform" in css
