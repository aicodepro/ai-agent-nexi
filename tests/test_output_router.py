import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_short_output_stays_main_ui():
    from engine.output_router import route_assistant_output
    result = route_assistant_output("Short answer.")
    assert result["show_workspace"] is False


def test_long_output_opens_workspace():
    from engine.output_router import route_assistant_output
    result = route_assistant_output("word " * 200)
    assert result["show_workspace"] is True
    assert result["main_ui_text"] == "I've prepared it in the workspace."


def test_code_output_opens_workspace():
    from engine.output_router import route_assistant_output
    result = route_assistant_output("```python\nprint('hi')\n```")
    assert result["show_workspace"] is True
    assert result["workspace_type"] == "code"


def test_workspace_spoken_text_is_short():
    from engine.output_router import route_assistant_output
    result = route_assistant_output("word " * 200)
    assert len(result["spoken_text"]) < 100
