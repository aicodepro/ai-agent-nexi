from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# test_chat_offcanvas_scrolls_and_does_not_replace_main_ui was deleted: the offcanvas chat
# drawer is genuinely gone from the redesigned Mark-style HUD. Grepped index.html,
# style.css, controller.js, main.js, hud_orb.js, hud_layers.js, studio_panel.js, and
# claude_terminal.js in www_mark/ for "offcanvas" (case-insensitive) — zero hits anywhere.
# Conversation now renders inline in #TranscriptCard / #nexi-log (the activity log), fed
# by a single command bar, so there is no separate scrolling chat panel to test.


def test_main_ui_keeps_single_input_bar():
    index = (ROOT / "www_mark" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "www_mark" / "style.css").read_text(encoding="utf-8")
    # The single text input is id="command-input" (not "TextInput") and its containing
    # .command-group is width-bounded via max-width: 700px (not the old min(820px, ...)).
    assert index.count('id="command-input"') == 1
    assert index.count('type="text"') == 1
    assert "max-width: 700px" in css
