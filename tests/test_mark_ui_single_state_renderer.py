from __future__ import annotations

from pathlib import Path



def test_mark_ui_single_state_renderer_targets_exist():
    root = Path(__file__).resolve().parents[1]
    html = (root / "www_mark" / "index.html").read_text(encoding="utf-8")
    js = (root / "www_mark" / "controller.js").read_text(encoding="utf-8")

    assert "window.jarvisApplyState" in js
    for dom_id in ["jarvis-state", "jarvis-source", "jarvis-log", "jarvis-bottom-state", "jarvis-center-state", "jarvis-status-badge"]:
        assert dom_id in html
    assert "updateMainHudState(state, label)" in js
    assert "updateBottomState(state, label)" in js
    assert "updateStatusBadge(state, label)" in js
