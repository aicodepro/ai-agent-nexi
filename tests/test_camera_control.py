import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock, PropertyMock
import pytest


@pytest.fixture(autouse=True)
def _reset_mouse_state(monkeypatch):
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control.mouse_actions import _reset_state
    _reset_state()
    yield


def test_import_camera_control_no_crash():
    from engine.camera_control import is_camera_control_running, start_camera_control, stop_camera_control
    assert is_camera_control_running() is False


def test_start_stop_no_real_camera():
    from engine.camera_control import start_camera_control, stop_camera_control, is_camera_control_running
    assert not is_camera_control_running()


def test_gpu_detection_no_torch_does_not_crash():
    from engine.camera_control.gpu import detect_gpu
    fake_cv2 = MagicMock()
    fake_cv2.cuda.getCudaEnabledDeviceCount.return_value = 0
    with patch.dict(os.environ, {"CAMERA_USE_GPU": "true"}, clear=False):
        with patch.dict("sys.modules", {"cv2": fake_cv2, "torch": None}):
            with patch("engine.camera_control.gpu.probe_mediapipe_gpu", return_value={"mediapipe_gpu": False, "xnnpack": True, "error": None}):
                result = detect_gpu()
    assert isinstance(result, dict)
    assert "available" in result
    assert "backend" in result


def test_gpu_disabled_by_env():
    from engine.camera_control.gpu import detect_gpu
    with patch.dict(os.environ, {"CAMERA_USE_GPU": "false"}, clear=False):
        result = detect_gpu()
        assert result["available"] is False
        assert result["backend"] == "cpu"


def test_detect_gpu_returns_dict():
    from engine.camera_control.gpu import detect_gpu
    with patch.dict(os.environ, {"CAMERA_USE_GPU": "false"}, clear=False):
        result = detect_gpu()
    for key in ("available", "backend", "device", "cuda_torch", "cuda_opencv", "name"):
        assert key in result, f"missing key: {key}"


def test_smoothing_filter_basic():
    from engine.camera_control.smoothing import SmoothingFilter
    sf = SmoothingFilter(factor=0.5, deadzone=0.0)
    x1, y1 = sf.update(100, 200)
    assert x1 == 100.0
    assert y1 == 200.0
    x2, y2 = sf.update(200, 300)
    assert x2 == 150.0
    assert y2 == 250.0


def test_smoothing_filter_deadzone():
    from engine.camera_control.smoothing import SmoothingFilter
    sf = SmoothingFilter(factor=0.5, deadzone=20.0)
    sf.update(100, 200)
    x, y = sf.update(105, 205)
    assert x == 100.0
    assert y == 200.0


def test_smoothing_reset():
    from engine.camera_control.smoothing import SmoothingFilter
    sf = SmoothingFilter(factor=0.5, deadzone=0.0)
    sf.update(100, 200)
    sf.reset()
    x, y = sf.update(500, 600)
    assert x == 500.0
    assert y == 600.0


def test_gaze_smoothing_basic():
    from engine.camera_control.smoothing import GazeSmoothingFilter
    gf = GazeSmoothingFilter(factor=0.6, deadzone=0.0)
    x1, y1 = gf.update(100, 200)
    assert x1 == 100.0
    assert y1 == 200.0
    gf.update(200, 300)
    gf.update(300, 400)
    gf.update(400, 500)
    x5, y5 = gf.update(500, 600)
    assert x5 > 100.0
    assert y5 > 200.0


def test_gaze_smoothing_reset():
    from engine.camera_control.smoothing import GazeSmoothingFilter
    gf = GazeSmoothingFilter(factor=0.6, deadzone=0.0)
    gf.update(100, 200)
    gf.reset()
    x, y = gf.update(999, 888)
    assert x == 999.0
    assert y == 888.0


@patch("engine.camera_control.mouse_actions.pyautogui.moveTo")
def test_mouse_move(mock_move):
    from engine.camera_control.mouse_actions import move_cursor
    move_cursor(500, 300)
    mock_move.assert_called_once()


@patch("engine.camera_control.mouse_actions.pyautogui.click")
def test_left_click_cooldown(mock_click):
    from engine.camera_control.mouse_actions import left_click
    left_click()
    assert mock_click.call_count == 1
    left_click()
    assert mock_click.call_count == 1


@patch("engine.camera_control.mouse_actions.pyautogui.doubleClick")
@patch("engine.camera_control.mouse_actions.pyautogui.click")
def test_double_click(mock_click, mock_double):
    from engine.camera_control.mouse_actions import double_click
    result = double_click()
    assert result is True
    mock_double.assert_called_once_with(button="left")
    mock_click.assert_not_called()


@patch("engine.camera_control.mouse_actions.pyautogui.mouseUp")
@patch("engine.camera_control.mouse_actions.pyautogui.mouseDown")
def test_drag_start_stop(mock_down, mock_up):
    from engine.camera_control.mouse_actions import start_drag, stop_drag, is_dragging
    start_drag()
    mock_down.assert_called_once()
    assert is_dragging() is True
    stop_drag()
    mock_up.assert_called_once()
    assert is_dragging() is False


@patch("engine.camera_control.mouse_actions.pyautogui.scroll")
def test_scroll(mock_scroll):
    from engine.camera_control.mouse_actions import scroll
    scroll(50)
    mock_scroll.assert_called_once()


@patch("engine.camera_control.mouse_actions.pyautogui.click")
def test_right_click(mock_click):
    from engine.camera_control.mouse_actions import right_click
    right_click()
    mock_click.assert_called_once_with(button="right")


@patch("engine.camera_control.mouse_actions.pyautogui.screenshot")
def test_screenshot(mock_ss):
    from engine.camera_control.mouse_actions import screenshot
    mock_ss.return_value = MagicMock()
    result = screenshot()
    mock_ss.assert_called_once()
    assert isinstance(result, str)


def test_hand_controller_import():
    from engine.camera_control.hand_controller import HandController, GESTURE_IDLE
    import threading
    stop_evt = threading.Event()
    stop_evt.set()
    ctrl = HandController(stop_event=stop_evt)
    assert ctrl is not None
    ctrl.stop()


def test_eye_controller_import():
    from engine.camera_control.eye_controller import EyeController
    import threading
    stop_evt = threading.Event()
    stop_evt.set()
    ctrl = EyeController(stop_event=stop_evt)
    assert ctrl is not None
    ctrl.stop()


def test_ear_calculation():
    from engine.camera_control.eye_controller import EyeController


    class MockLandmark:
        def __init__(self, x, y, z=0):
            self.x = x
            self.y = y
            self.z = z

    open_eye = [MockLandmark(0, 0.5), MockLandmark(0.1, 0.3), MockLandmark(0.2, 0.3),
                MockLandmark(0.3, 0.5), MockLandmark(0.2, 0.7), MockLandmark(0.1, 0.7)]
    ear_open = EyeController._calculate_ear(open_eye)
    assert ear_open > 0.2

    closed_eye = [MockLandmark(0, 0.5), MockLandmark(0.1, 0.48), MockLandmark(0.2, 0.48),
                  MockLandmark(0.3, 0.5), MockLandmark(0.2, 0.52), MockLandmark(0.1, 0.52)]
    ear_closed = EyeController._calculate_ear(closed_eye)
    assert ear_closed < ear_open


def test_get_distance():
    from engine.camera_control.hand_controller import HandController
    d = HandController._get_distance((0, 0), (3, 4))
    assert d == 5.0
    d2 = HandController._get_distance((1, 1), (1, 1))
    assert d2 == 0.0


def test_is_open_palm():
    from engine.camera_control.hand_controller import HandController
    import threading
    ctrl = HandController(stop_event=threading.Event())
    landmarks = [(0.5, 0.4)] * 5 + [(0.5, 0.6)] * 5 + [(0.5, 0.4)] * 5 + [(0.5, 0.6)] * 6
    ratio = ctrl._is_open_palm(landmarks[:21])
    assert 0.0 <= ratio <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
