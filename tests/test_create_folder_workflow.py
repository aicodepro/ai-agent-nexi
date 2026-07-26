import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path
from unittest.mock import patch

import pytest

from engine import workflow_state
from engine.create_folder_workflow import (
    start_create_folder,
    handle_workflow_reply,
    ALLOWED_PROMPT,
)


@pytest.fixture(autouse=True)
def _clear_workflow():
    workflow_state.clear_workflow()
    yield
    workflow_state.clear_workflow()


@pytest.fixture
def home(tmp_path, monkeypatch):
    # Redirect Path.home() so no real Desktop folders are ever created.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


# --- slot-filling flow ------------------------------------------------------

def test_create_folder_without_details_asks_name():
    msg = start_create_folder("create folder")
    assert "name" in msg.lower()
    assert workflow_state.get_workflow()["step"] == "ask_name"


def test_folder_name_reply_asks_location():
    start_create_folder("create folder")
    msg = handle_workflow_reply("Batch Three Test Folder")
    assert "where" in msg.lower()
    assert "Batch Three Test Folder" in msg
    assert workflow_state.get_workflow()["step"] == "ask_location"


def test_location_reply_asks_confirmation():
    start_create_folder("create folder")
    handle_workflow_reply("Batch Three Test Folder")
    msg = handle_workflow_reply("Desktop")
    assert msg == "Create Batch Three Test Folder on Desktop?"
    assert workflow_state.get_workflow()["step"] == "confirm"


def test_yes_creates_folder(home):
    start_create_folder("create folder")
    handle_workflow_reply("Batch Three Test Folder")
    handle_workflow_reply("Desktop")
    msg = handle_workflow_reply("yes")
    # The confirmation must name what was created and where. "Done. Folder
    # created." told a user who cannot see the screen nothing at all.
    assert "Batch Three Test Folder" in msg
    assert "Desktop" in msg
    assert (home / "Desktop" / "Batch Three Test Folder").is_dir()
    assert workflow_state.has_active_workflow() is False


def test_no_cancels_workflow(home):
    start_create_folder("create folder")
    handle_workflow_reply("My Folder")
    handle_workflow_reply("Desktop")
    msg = handle_workflow_reply("no")
    assert msg == "Cancelled."
    assert workflow_state.has_active_workflow() is False
    assert not (home / "Desktop" / "My Folder").exists()


def test_cancel_clears_workflow():
    for word in ("cancel", "stop", "never mind", "exit", "leave it"):
        start_create_folder("create folder")
        msg = handle_workflow_reply(word)
        assert msg == "Cancelled.", f"{word!r} should cancel"
        assert workflow_state.has_active_workflow() is False


def test_direct_command_with_name_and_location_asks_confirmation():
    msg = start_create_folder("create folder Test Folder on Desktop")
    assert msg == "Create Test Folder on Desktop?"
    assert workflow_state.get_workflow()["step"] == "confirm"


def test_reply_during_workflow_does_not_go_to_qa(home):
    import engine.command as command
    start_create_folder("create folder")  # active at ask_name
    with patch("engine.features.chatBot") as mock_chat, \
         patch("engine.command.eel"), \
         patch("engine.command.speak") as mock_speak:
        command.allCommands("Batch Three Test Folder")
        mock_chat.assert_not_called()
        mock_speak.assert_called_once()
    wf = workflow_state.get_workflow()
    assert wf is not None and wf["step"] == "ask_location"


def test_unknown_location_reprompts_allowed_locations():
    start_create_folder("create folder")
    handle_workflow_reply("My Folder")
    msg = handle_workflow_reply("Mars")
    assert msg == ALLOWED_PROMPT
    assert workflow_state.get_workflow()["step"] == "ask_location"


def test_dangerous_path_rejected(home):
    start_create_folder("create folder")
    handle_workflow_reply("My Folder")
    for bad in ("C:\\", "C:\\Windows", "System32", "Program Files"):
        msg = handle_workflow_reply(bad)
        assert msg == ALLOWED_PROMPT, f"{bad!r} should be rejected"
        assert workflow_state.get_workflow()["step"] == "ask_location"
    assert not (home / "Windows").exists()


def test_invalid_folder_name_rejected():
    start_create_folder("create folder")
    for bad in ("CON", "..", "bad/name", "bad\\name", ""):
        msg = handle_workflow_reply(bad)
        assert workflow_state.get_workflow()["step"] == "ask_name"
        assert "Done" not in msg


def test_existing_folder_reports_exists(home):
    (home / "Desktop" / "Dup Folder").mkdir(parents=True)
    start_create_folder("create folder Dup Folder on Desktop")
    msg = handle_workflow_reply("yes")
    assert msg == "That folder already exists."
    assert workflow_state.has_active_workflow() is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
