import os
import sys
from pathlib import Path

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


def test_start_camera_missing_mode_asks_preview_or_control(monkeypatch):
    import engine.tool_registry as registry

    monkeypatch.setattr(registry, "_execute_handler", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("hardware started")))
    from engine.tool_registry import select_tool, execute_tool
    selected = select_tool("start hand gesture control")
    for name, slots in [(selected["name"], selected["slots"]), ("eye_mouse_control", {})]:
        result = execute_tool(name, slots)
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
    assert result["expects_user_reply"] is True
    assert "mouse" not in result["message"].lower()
    assert result["success"] is False


def test_safety_gate_failure_fails_closed(monkeypatch, capsys):
    import engine.safety_gate as safety_gate
    import engine.tool_registry as registry

    def fail(*_args, **_kwargs):
        raise RuntimeError("gate unavailable")

    monkeypatch.setattr(safety_gate, "execution_is_safe", fail)
    monkeypatch.setattr(registry, "_execute_handler", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("executed")))

    result = registry.execute_tool("system_status", {})

    assert result["success"] is False
    assert result["error_code"] == "SAFETY_GATE_ERROR"
    assert "[SAFETY] fail_closed" in capsys.readouterr().out


def test_safety_gate_import_failure_fails_closed(monkeypatch):
    import sys
    import engine.tool_registry as registry

    monkeypatch.setitem(sys.modules, "engine.safety_gate", None)
    monkeypatch.setattr(registry, "_execute_handler", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("executed")))

    result = registry.execute_tool("system_status", {})

    assert result["success"] is False
    assert result["error_code"] == "SAFETY_GATE_ERROR"


def test_model_confirmed_metadata_cannot_bypass_confirmation(monkeypatch):
    import engine.tool_registry as registry

    monkeypatch.setattr(registry, "_execute_handler", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("executed")))
    result = registry.execute_tool("clipboard_write_safe", {"text": "hello", "confirmed": True})

    assert result["requires_confirmation"] is True
    assert result["expects_user_reply"] is True


def test_unknown_tool_returns_structured_rejection():
    from engine.tool_registry import execute_tool

    result = execute_tool("not_registered", {})

    assert result["handled"] is True
    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_TOOL"
    assert result["expects_user_reply"] is False


def test_create_folder_rejects_path_outside_desktop(tmp_path, monkeypatch):
    from engine.tool_registry import execute_tool

    # The LLM safety gate blocks medium+ tools when offline, before the path check
    # under test is ever reached. Disable it so this asserts the confinement itself.
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")

    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    outside = tmp_path / "outside"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = execute_tool("create_folder", {"folder_name": str(outside)})

    assert result["success"] is False
    assert result["error_code"] == "PATH_OUTSIDE_SAFE_ROOT"
    assert not outside.exists()


def test_create_file_rejects_path_outside_desktop(tmp_path, monkeypatch):
    from engine.tool_registry import execute_tool

    # The LLM safety gate blocks medium+ tools when offline, before the path check
    # under test is ever reached. Disable it so this asserts the confinement itself.
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")

    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    outside = tmp_path / "outside.txt"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = execute_tool("create_file", {"file_name": str(outside), "content": "nope"})

    assert result["success"] is False
    assert result["error_code"] == "PATH_OUTSIDE_SAFE_ROOT"
    assert not outside.exists()


def test_reserved_metadata_filter_preserves_declared_tool_slots(monkeypatch):
    import engine.safety_gate as safety_gate
    import engine.tool_registry as registry

    seen = {}
    monkeypatch.setitem(
        registry._TOOLS,
        "authorization_test",
        registry._spec("authorization_test", "test", ["authorization"]),
    )
    monkeypatch.setattr(safety_gate, "execution_is_safe", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(
        registry,
        "_execute_handler",
        lambda _name, slots, **_kwargs: seen.update(slots) or {"success": True, "verified": True},
    )

    result = registry.execute_tool("authorization_test", {"authorization": "document-owner"})

    assert result["success"] is True
    assert seen["authorization"] == "document-owner"


def test_every_high_risk_tool_has_a_user_in_the_loop_gate():
    """No high/critical tool may run off a model's say-so alone.

    Two gates qualify: a confirmation prompt, or the approval queue (submit -> the user
    calls approve_action -> re-invoked with an internal token). The queue is the stronger
    of the two, so queue-gated tools are deliberately exempt from the confirm prompt —
    but having NEITHER is never acceptable.

    Asserted statically: executing every high-risk tool to observe the gate would really
    click, type, and launch things on the machine running the suite.
    """
    from engine.approval_queue import is_queue_gated
    from engine.tool_registry import _TOOLS

    ungated = [
        name for name, spec in _TOOLS.items()
        if spec.enabled and str(spec.safety).lower() in {"high", "critical"}
        and not spec.requires_confirmation and not is_queue_gated(spec.handler)
    ]
    assert not ungated, f"high-risk tools with no user-in-the-loop gate: {ungated}"


def test_queue_gated_tool_is_queued_not_silently_executed(monkeypatch):
    """The carve-out above must still stop the action — it defers to the queue, not to nothing."""
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")
    import engine.approval_queue as aq
    from engine.tool_registry import execute_tool

    aq.clear()
    result = execute_tool("click_ui_element", {"target": "submit"})
    assert result.get("requires_approval") is True, f"click ran without approval: {result}"
    assert result.get("verified") is not True
    aq.clear()
