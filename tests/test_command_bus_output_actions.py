import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_command_copy_it_uses_latest_output():
    from engine.command_bus import submit_user_command
    with patch("engine.command._handle_output_command", return_value=True) as mock_output:
        assert submit_user_command("copy it", source="typed") is True
    mock_output.assert_called_once()


def test_command_create_file_asks_filename():
    from engine.command import _handle_output_command
    from engine import output_actions
    output_actions.set_latest_output("hello", "Test Output")
    try:
        with patch("engine.command.speak") as mock_speak:
            assert _handle_output_command("create a file") is True
    finally:
        output_actions._latest_output = {}
    assert "What should I name the file?" in mock_speak.call_args.args[0]
