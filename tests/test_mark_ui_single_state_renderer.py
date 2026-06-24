from __future__ import annotations

from pathlib import Path



def test_mark_ui_single_state_renderer_targets_exist():
    root = Path(__file__).resolve().parents[1]
    html = (root / "www_mark" / "index.html").read_text(encoding="utf-8")
    js = (root / "www_mark" / "controller.js").read_text(encoding="utf-8")

    assert "window.nexiApplyState" in js
    for dom_id in ["nexi-state", "nexi-source", "nexi-log", "nexi-bottom-state", "nexi-center-state", "nexi-status-badge"]:
        assert dom_id in html
    assert "updateMainHudState(state, label)" in js
    assert "updateBottomState(state, label)" in js
    assert "updateStatusBadge(state, label)" in js
