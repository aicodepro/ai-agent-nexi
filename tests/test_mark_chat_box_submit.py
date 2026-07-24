from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mark_chat_uses_ui_submit_text_and_immediate_sender_text():
    text = (ROOT / "www_mark" / "main.js").read_text(encoding="utf-8")
    assert "eel.ui_submit_text(text)" in text
    assert "window.senderText" in text


def test_mark_chat_enter_and_send_button_submit():
    text = (ROOT / "www_mark" / "main.js").read_text(encoding="utf-8")
    assert "e.key === 'Enter'" in text
    assert "sendBtn.addEventListener('click'" in text


def test_mark_ui_no_direct_allcommands_call():
    text = (ROOT / "www_mark" / "main.js").read_text(encoding="utf-8")
    assert "eel.allCommands" not in text
