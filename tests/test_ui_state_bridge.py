import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.runtime_bridge import EVENT_COMMAND_TEXT, EVENT_STATUS, handle_bridge_event


ROOT = Path(__file__).resolve().parents[1]


def _ui_payloads(mock_update):
    payloads = []
    for call in mock_update.call_args_list:
        raw = call.args[0]
        payloads.append(raw)
    return payloads


def test_asr_started_posts_transcribing_status():
    event = {"type": EVENT_STATUS, "status": "asr_started", "source": "hotword"}
    with patch("eel.updateJarvisState", create=True) as mock_update:
        handle_bridge_event(event)
    assert _ui_payloads(mock_update)[0]["state"] == "recognising"


def test_asr_result_posts_transcript_preview():
    event = {"type": EVENT_STATUS, "status": "asr_result", "source": "clap", "text": "hello"}
    with patch("eel.updateJarvisState", create=True) as mock_update:
        handle_bridge_event(event)
    payload = _ui_payloads(mock_update)[0]
    assert payload["state"] == "recognising"
    assert payload["text"] == "hello"


def test_command_text_sets_thinking_then_dispatches_allCommands():
    event = {"type": EVENT_COMMAND_TEXT, "text": "hello", "source": "hotword"}
    with patch("eel.updateJarvisState", create=True) as mock_update, \
         patch("engine.command.allCommands") as mock_all:
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert payloads[0]["state"] == "thinking"
    mock_all.assert_called_once_with("hello")


def test_command_text_returns_ui_to_idle_after_dispatch():
    event = {"type": EVENT_COMMAND_TEXT, "text": "hello", "source": "clap"}
    with patch("eel.updateJarvisState", create=True) as mock_update, \
         patch("engine.command.allCommands"):
        handle_bridge_event(event)
    payloads = _ui_payloads(mock_update)
    assert payloads[-1]["state"] == "sleep"


def test_core_ui_functions_exist_in_js():
    text = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    assert "function DisplayMessage" in text
    assert "function senderText" in text
    assert "function receiverText" in text
    assert "function setStatus" in text
    assert "function sourceLabel" in text
    assert "function ShowHood" in text


def test_idle_hint_mentions_hey_jarvis_and_double_clap():
    html = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    combined = f"{html}\n{js}".lower()
    assert "hey jarvis" in combined
    assert "double clap" in combined
