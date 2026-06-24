import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_which_topic_sets_followup():
    from engine import followup_manager as fm
    fm.clear_followup("test")
    fm.set_pending_followup("Which topic, sir?", "essay_topic", "brain")
    assert fm.has_pending_followup() is True
    fm.clear_followup("test")


def test_followup_answer_routes_to_brain_continuation():
    from engine import followup_manager as fm
    fm.clear_followup("test")
    fm.set_pending_followup("Which topic, sir?", "essay_topic", "brain")
    result = fm.consume_followup_answer("AI agents", "typed")
    assert result["handled"] is True
    assert result["route"] == "brain_continuation"
    assert result["text"] == "write an essay about AI agents"
    assert fm.has_pending_followup() is False


def test_folder_question_sets_workflow_followup():
    from engine import followup_manager as fm
    fm.clear_followup("test")
    fm.set_pending_followup("What should I name the folder?", "folder_name", "workflow")
    result = fm.consume_followup_answer("Demo Folder", "typed")
    assert result["handled"] is True
    assert result["route"] == "workflow"
    assert result["text"] == "Demo Folder"


def test_cancel_clears_followup():
    from engine import followup_manager as fm
    fm.clear_followup("test")
    fm.set_pending_followup("Which topic, sir?", "essay_topic", "brain")
    result = fm.consume_followup_answer("cancel", "typed")
    assert result["cancelled"] is True
    assert fm.has_pending_followup() is False
