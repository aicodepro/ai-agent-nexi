from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_orb_size_limited():
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    assert "width: min(240px, 32vw)" in css
    assert "max-width: 240px" in css


def test_input_bar_near_bottom():
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    assert "position: fixed" in css
    assert "bottom: 20px" in css
