import pytest
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _disable_llm_safety_gate(monkeypatch):
    """The LLM safety gate calls the Groq safety model. Offline (no GROQ_API_KEY) it fails
    CLOSED and blocks every medium+ risk tool, so nothing here would reach the approval /
    confirmation logic these tests exist to check. Disable it locally rather than suite-wide:
    a blocked tool is the SAFE default for a test run, since an allowed one really launches
    apps and moves the mouse."""
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")




def test_hand_gesture_preview_does_not_move_mouse():
    from engine.tool_registry import execute_tool
    with patch("engine.camera_control.start_camera_control") as mock_control:
        result = execute_tool("hand_gesture_control", {"mode": "preview"})
    assert result["ok"] is True
    mock_control.assert_not_called()


def test_hand_gesture_control_requires_explicit_command():
    from engine.camera_control import start_hand_gesture_control
    assert start_hand_gesture_control(mode="control", explicit=False) is False


def test_stop_camera_control_stops_hand_and_eye(capsys):
    from engine.camera_control import stop_all_controls
    assert stop_all_controls("test") is True
    out = capsys.readouterr().out
    assert "[GESTURE] stopped reason=test" in out
    assert "[EYE] stopped reason=test" in out
