import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tool_registry_contains_core_tools():
    from engine.tool_registry import get_tool
    for name in ["open_app", "open_website", "web_search", "create_folder", "create_file", "take_screenshot", "remember", "repeat_last", "system_status"]:
        assert get_tool(name) is not None


def test_tool_registry_contains_hand_gesture_tools():
    from engine.tool_registry import get_tool
    for name in ["camera_preview", "hand_gesture_control", "stop_camera_control", "gesture_click_mode", "gesture_scroll_mode"]:
        assert get_tool(name) is not None


def test_tool_registry_contains_eye_mouse_tools():
    from engine.tool_registry import get_tool
    for name in ["eye_mouse_control", "eye_mouse_calibrate"]:
        assert get_tool(name) is not None


def test_open_missing_app_asks_clarification():
    from engine.tool_registry import execute_tool
    result = execute_tool("open_app", {})
    assert result["expects_user_reply"] is True
    assert result["message"] == "Which app should I open?"


def test_search_missing_query_asks_clarification():
    from engine.tool_registry import execute_tool
    result = execute_tool("web_search", {})
    assert result["expects_user_reply"] is True
    assert result["message"] == "What should I search for?"


def test_start_camera_missing_mode_asks_preview_or_control():
    from engine.tool_registry import select_tool, execute_tool
    selected = select_tool("start hand gesture control")
    result = execute_tool(selected["name"], selected["slots"])
    assert result["expects_user_reply"] is True
    assert result["message"] == "Preview or control mode?"


def test_safety_required_for_mouse_control():
    from engine.tool_registry import get_tool, execute_tool
    assert get_tool("hand_gesture_control")["requires_confirmation"] is True
    result = execute_tool("hand_gesture_control", {"mode": "control"})
    assert result["requires_confirmation"] is True


def test_safety_required_for_direct_clipboard_write():
    from engine.tool_registry import execute_tool

    result = execute_tool("clipboard_write_safe", {"text": "hello"})
    assert result["requires_confirmation"] is True
    assert result["success"] is False
