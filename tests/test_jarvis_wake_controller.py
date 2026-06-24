import os
import queue
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_wake_jarvis_returns_true():
    """wake_jarvis no longer posts status events — they are emitted by
    the AudioWakePipeline signal bus instead."""
    from engine.jarvis_wake_controller import set_wake_queue, wake_jarvis, sleep_jarvis, is_jarvis_awake

    q = queue.Queue()
    set_wake_queue(q)
    assert wake_jarvis("hotword") is True
    assert is_jarvis_awake() is True
    assert q.qsize() == 0
    sleep_jarvis("test")
    set_wake_queue(None)


def test_sleep_jarvis_posts_sleeping_status():
    from engine.jarvis_wake_controller import set_wake_queue, sleep_jarvis, is_jarvis_awake

    q = queue.Queue()
    set_wake_queue(q)
    assert sleep_jarvis("command") is True
    event = q.get_nowait()
    assert event["status"] == "sleeping"
    assert event["source"] == "system"
    assert is_jarvis_awake() is False
    set_wake_queue(None)


def test_sleep_command_sets_sleeping_state():
    import engine.command as command

    with patch("engine.jarvis_wake_controller.sleep_jarvis") as mock_sleep, \
         patch.object(command, "speak") as mock_speak, \
         patch.object(command, "eel"):
        command.allCommands("sleep")

    mock_sleep.assert_called_once_with(reason="command")
    mock_speak.assert_called_once_with("Sleeping.")
