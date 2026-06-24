import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_response_detects_question():
    from engine.assistant_response import response_asks_question
    assert response_asks_question("Which topic, sir?") is True
    assert response_asks_question("Please provide the folder name") is True
    assert response_asks_question("Done. Folder created.") is False


def test_brain_question_sets_expects_user_reply():
    from engine.assistant_response import make_response
    response = make_response("Which topic, sir?", source="brain")
    assert response["expects_user_reply"] is True
    assert response["followup_type"] == "essay_topic"
    assert response["ui_state_after"] == "listening"
    assert response["source"] == "brain"


def test_response_envelope_long_answer_uses_summary():
    from engine.assistant_response import make_response
    full = "Cake recipe. " + ("Mix and bake. " * 80)
    response = make_response(full, source="brain")
    assert response["display_text"] == full
    assert len(response["spoken_text"]) < len(full)
    assert "on screen" in response["spoken_text"]
