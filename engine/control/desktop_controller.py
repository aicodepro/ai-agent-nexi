from engine.control.base import ControlResult, ControlFunction
from engine.control.process_controller import start_process, kill_process, list_running

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def handle_open_app(app_name=None, **_):
    if not app_name:
        return ControlResult.failure(
            message="No app name specified",
            code="MISSING_ENTITY"
        )
    return start_process(app_name)


def handle_close_app(app_name=None, **_):
    if not app_name:
        return ControlResult.failure(
            message="No app name specified",
            code="MISSING_ENTITY"
        )
    return kill_process(app_name)


def handle_focus_app(app_name=None, **_):
    if not app_name:
        return ControlResult.failure(
            message="No app name specified",
            code="MISSING_ENTITY"
        )
    if not HAS_WIN32:
        return ControlResult.failure(
            message="win32gui not available for window focus",
            code="MISSING_DEPENDENCY"
        )
    try:

        def enum_windows_proc(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if app_name.lower() in title.lower():
                    windows.append(hwnd)

        windows = []
        win32gui.EnumWindows(enum_windows_proc, windows)
        if windows:
            win32gui.ShowWindow(windows[0], win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(windows[0])
            return ControlResult.success(message=f"Focused {app_name.title()}")
        return ControlResult.failure(
            message=f"No window found matching '{app_name}'",
            code="WINDOW_NOT_FOUND"
        )
    except Exception as e:
        return ControlResult.failure(
            message=f"Failed to focus {app_name}",
            code="FOCUS_FAILED",
            error_message=str(e)
        )


def handle_list_apps(**_):
    return list_running()


def register_desktop_controls(registry):
    registry.register(
        ControlFunction(
            name="open_app",
            intent="open application",
            description="Open a known application (Chrome, Notepad, VS Code, File Explorer, etc.)",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["app_name"],
            optional_entities=[],
            handler=handle_open_app
        ),
        extra_keywords=["launch", "start", "open", "run"]
    )
    registry.register(
        ControlFunction(
            name="close_app",
            intent="close application",
            description="Close a known application by name",
            risk_level="HIGH",
            privacy_sensitivity="LOW",
            requires_confirmation=True,
            required_entities=["app_name"],
            optional_entities=[],
            handler=handle_close_app
        ),
        extra_keywords=["close", "kill", "exit", "quit", "stop"]
    )
    registry.register(
        ControlFunction(
            name="focus_app",
            intent="focus application",
            description="Bring an application window to the foreground",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["app_name"],
            optional_entities=[],
            handler=handle_focus_app
        ),
        extra_keywords=["focus", "switch to", "bring to front"]
    )
    registry.register(
        ControlFunction(
            name="list_apps",
            intent="list running applications",
            description="List all running applications",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=[],
            optional_entities=[],
            handler=handle_list_apps
        ),
        extra_keywords=["running", "list", "show apps", "applications"]
    )
