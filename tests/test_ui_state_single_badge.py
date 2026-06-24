from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_only_one_status_badge_visible():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    assert index.count('id="SourceBadge"') == 1


def test_tts_does_not_show_listening_badge():
    js = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    assert "badge.textContent = state.toUpperCase()" in js
    assert "sourceLabel(source)" not in js.split("if (badge)", 1)[1].split("if (preview)", 1)[0]


def test_context_active_not_main_badge():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    assert 'id="ContextIndicator"' in index
    assert 'id="SourceBadge"' in index


def test_idle_state_clean():
    js = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    assert "sleeping: 'SLEEPING'" in js


def test_speaking_state_clean():
    js = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    assert "saying: 'SAYING'" in js
