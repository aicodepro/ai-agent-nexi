import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_typed_and_voice_use_same_command_bus():
    from engine.command_bus import submit_user_command
    with patch("engine.command.allCommands") as mock_all:
        submit_user_command("search ronaldo", source="typed", mode="typed")
        submit_user_command("search messi", source="hotword", mode="voice")
    assert mock_all.call_args_list[0].args == ("search ronaldo",)
    assert mock_all.call_args_list[1].args == ("search messi",)


def test_voice_command_posts_to_bridge_only():
    import multiprocessing
    from engine.audio_wake_pipeline import AudioWakePipeline
    q = multiprocessing.Queue()
    pipeline = AudioWakePipeline(command_queue=q, asr=lambda a, s: "search messi")
    with patch("engine.command.allCommands") as mock_all:
        pipeline.emit_command(b"\x00\x00" * 1600, source="clap")
    mock_all.assert_not_called()
    events = [q.get(timeout=1), q.get(timeout=1), q.get(timeout=1)]
    assert any(event["type"] == "command_text" and event["text"] == "search messi" for event in events)


def test_rejected_voice_does_not_dispatch():
    from engine.command_bus import submit_user_command
    with patch("engine.command.allCommands") as mock_all, patch("engine.command.speak") as mock_speak:
        assert submit_user_command("Sarıç", source="hotword", mode="voice") is False
    mock_all.assert_not_called()
    mock_speak.assert_called_once()
