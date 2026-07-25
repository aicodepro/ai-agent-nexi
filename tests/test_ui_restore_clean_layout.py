import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_orb_size_limited():
    css = (ROOT / "www_mark" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "www_mark" / "hud_orb.js").read_text(encoding="utf-8")
    # The orb is now a <canvas> whose size is capped in hud_orb.js's resize() (bounded by
    # the container and a hard pixel ceiling), not by a fixed CSS width. The canvas is
    # still constrained to its container via CSS.
    assert "max-width: 100%" in css and "max-height: 100%" in css
    assert re.search(r"Math\.min\([^)]*,\s*\d+\)", js), "orb resize() must cap its size"


def test_input_bar_near_bottom():
    css = (ROOT / "www_mark" / "style.css").read_text(encoding="utf-8")
    assert "position: fixed" in css
    # The command bar is pinned to the last row of the 3-row app-shell grid (the
    # bottom-most position) instead of being absolutely positioned with bottom:20px.
    assert re.search(r"\.command-bar\s*\{[^}]*grid-row:\s*3", css)
