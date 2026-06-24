from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_offcanvas_scrolls_and_does_not_replace_main_ui():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    assert 'id="offcanvasScrolling"' in index
    assert 'id="chat-canvas-body" class="offcanvas-body"' in index
    assert "overflow-y: auto" in css


def test_main_ui_keeps_single_input_bar():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    assert index.count('id="TextInput"') == 1
    assert "width: min(820px, calc(100vw - 80px))" in css
