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




def test_eye_mouse_requires_calibration_before_control():
    import engine.camera_control as camera
    camera._eye_calibrated = False
    assert camera.start_eye_mouse_control(mode="control", explicit=True) is False


def test_eye_mouse_preview_does_not_click():
    from engine.tool_registry import execute_tool
    with patch("engine.camera_control.start_camera_control") as mock_control:
        result = execute_tool("eye_mouse_control", {"mode": "preview"})
    assert result["ok"] is True
    mock_control.assert_not_called()


def test_eye_mouse_calibrate_enables_control_gate():
    import engine.camera_control as camera
    camera._eye_calibrated = False
    assert camera.calibrate_eye_mouse() is True
    assert camera._eye_calibrated is True
