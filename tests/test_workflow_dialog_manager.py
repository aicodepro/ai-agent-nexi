import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_create_folder_missing_name_asks_question():
    from engine.workflow_dialog_manager import start_workflow, cancel_workflow
    cancel_workflow("test")
    result = start_workflow("create_folder", "create a folder", "typed")
    assert result["response"] == "What should I name the folder?"
    assert result["expects_user_reply"] is True


def test_create_folder_missing_path_asks_question():
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, cancel_workflow
    cancel_workflow("test")
    start_workflow("create_folder", "create a folder", "typed")
    result = handle_workflow_turn("Demo Website", "typed")
    assert result["response"] == "Where should I create Demo Website?"
    assert result["expects_user_reply"] is True


def test_active_workflow_switches_to_brain_on_essay_request():
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, cancel_workflow
    cancel_workflow("test")
    start_workflow("create_folder", "create a folder", "typed")
    result = handle_workflow_turn("can you write an essay about solar system", "typed")
    assert result["switch"] is True
    assert result["planner"]["intent"] == "essay_request"


def test_cancel_clears_workflow():
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, has_active_workflow, cancel_workflow
    cancel_workflow("test")
    start_workflow("create_folder", "create a folder", "typed")
    result = handle_workflow_turn("cancel", "typed")
    assert result["response"] == "Cancelled."
    assert has_active_workflow() is False


def test_create_folder_slot_and_execution_logs(tmp_path, monkeypatch, capsys):
    from pathlib import Path
    from engine.workflow_dialog_manager import start_workflow, handle_workflow_turn, cancel_workflow
    cancel_workflow("test")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()
    start_workflow("create_folder", "create a folder", "typed")
    handle_workflow_turn("Demo Website", "typed")
    handle_workflow_turn("Desktop", "typed")
    result = handle_workflow_turn("yes", "typed")
    out = capsys.readouterr().out
    # Names what was created; a bare "Done." is useless without a screen.
    assert "Demo Website" in result["response"]
    assert "[WORKFLOW] slot_saved name=folder_name" in out
    assert "[WORKFLOW] slot_saved name=location" in out
    assert "[WORKFLOW] executed id=create_folder" in out
