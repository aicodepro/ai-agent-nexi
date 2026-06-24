import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tool_alias_youtube_to_website(monkeypatch, tmp_path):
    import engine.tool_usage_intelligence as tool_ai
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", tmp_path / "tools.json")
    alias = tool_ai.resolve_tool_alias("youtube")
    assert alias["handled"] is True
    assert alias["name"] == "open_website"
    assert alias["slots"]["url"] == "youtube.com"


def test_tool_result_required_for_done():
    from engine.assistant_response import guard_unverified_action_message
    text = guard_unverified_action_message("Done. Opened Chrome.", {"success": False})
    assert "couldn't verify" in text
