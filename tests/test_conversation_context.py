import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_keeps_last_10_turns():
    from engine.conversation_context import add_user_turn, add_assistant_turn, clear_recent_context, get_recent_turns
    clear_recent_context()
    for i in range(12):
        add_user_turn(f"u{i}", "typed")
        add_assistant_turn(f"a{i}")
    turns = get_recent_turns(limit=10)
    assert len(turns) == 10
    assert turns[0]["text"] == "u7"
    assert turns[-1]["text"] == "a11"


def test_recent_context_text_is_compact():
    from engine.conversation_context import add_turn, clear_recent_context, get_recent_context_text
    clear_recent_context()
    add_turn("user", "what is AI", source="typed")
    add_turn("assistant", "AI is software that performs tasks requiring intelligence.", source="brain")
    context = get_recent_context_text(limit=10, max_chars=80)
    assert len(context) <= 80
    assert "User:" in context


def test_find_recent_reference_latest_output():
    from engine.conversation_context import add_turn, clear_recent_context, find_recent_reference
    clear_recent_context()
    add_turn("assistant", "Long answer here", source="brain", metadata={"output_id": "out_1"})
    ref = find_recent_reference("make it shorter")
    assert ref is not None
    assert ref["text"] == "Long answer here"
    assert ref["output_id"] == "out_1"


def test_repeat_last_response_value():
    from engine.conversation_context import add_assistant_turn, clear_recent_context, get_last_assistant_response
    clear_recent_context()
    add_assistant_turn("Solar system answer")
    assert get_last_assistant_response() == "Solar system answer"
