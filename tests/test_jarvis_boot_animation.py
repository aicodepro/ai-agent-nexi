import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]


def test_startup_animation_classes_exist():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    controller = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    assert "Jarvis" in index
    assert "jarvis" in controller.lower()
    assert "style.css" in index


def test_state_animation_selectors_exist():
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    assert ".jarvis-state" in css
    assert "@keyframes" in css
    assert "waveform" in css
