import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_local_action_does_not_call_gemini():
    import engine.command as command

    with patch("engine.local_skills.subprocess.Popen"), patch("engine.command.speak"), patch("engine.command.safe_eel_call"), patch("engine.features.chatBot") as mock_chatbot:
        command.allCommands("open chrome")

    mock_chatbot.assert_not_called()


def test_open_youtube_selects_open_website():
    from engine.tool_registry import select_tool

    selected = select_tool("open youtube")
    assert selected["handled"] is True
    assert selected["name"] == "open_website"
    assert selected["slots"]["url"] == "youtube.com"


def test_search_ronaldo_selects_web_search():
    from engine.tool_registry import select_tool

    selected = select_tool("search ronaldo")
    assert selected["handled"] is True
    assert selected["name"] == "web_search"
    assert selected["slots"]["query"] == "ronaldo"
