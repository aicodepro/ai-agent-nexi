from src.orin.control.base import ControlResult, ControlFunction

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def _get_visible_windows():
    if not HAS_WIN32:
        return []
    windows = []

    def enum_proc(hwnd, result):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                result.append({"hwnd": hwnd, "title": title})
    win32gui.EnumWindows(enum_proc, windows)
    return windows


def handle_get_active_window(**_):
    if not HAS_WIN32:
        return ControlResult.failure(
            message="win32gui not available",
            code="MISSING_DEPENDENCY"
        )
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        return ControlResult.success(
            message=f"Active window: {title}",
            data={"title": title, "hwnd": hwnd}
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to get active window",
            code="WINDOW_ERROR",
            error_message=str(e)
        )


def handle_list_windows(**_):
    windows = _get_visible_windows()
    return ControlResult.success(
        message=f"Found {len(windows)} visible windows",
        data={"windows": [{"title": w["title"]} for w in windows]}
    )


def handle_focus_window(title=None, **_):
    if not title:
        return ControlResult.failure(
            message="No window title specified",
            code="MISSING_ENTITY"
        )
    if not HAS_WIN32:
        return ControlResult.failure(
            message="win32gui not available",
            code="MISSING_DEPENDENCY"
        )
    try:
        windows = _get_visible_windows()
        for w in windows:
            if title.lower() in w["title"].lower():
                win32gui.ShowWindow(w["hwnd"], win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(w["hwnd"])
                return ControlResult.success(
                    message=f"Focused window: {w['title']}",
                    data={"title": w["title"]}
                )
        return ControlResult.failure(
            message=f"No window found matching '{title}'",
            code="WINDOW_NOT_FOUND"
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to focus window",
            code="FOCUS_FAILED",
            error_message=str(e)
        )


def handle_minimize_window(title=None, **_):
    if not HAS_WIN32:
        return ControlResult.failure(
            message="win32gui not available",
            code="MISSING_DEPENDENCY"
        )
    try:
        if title:
            windows = _get_visible_windows()
            for w in windows:
                if title.lower() in w["title"].lower():
                    win32gui.ShowWindow(w["hwnd"], win32con.SW_MINIMIZE)
                    return ControlResult.success(
                        message=f"Minimized window: {w['title']}"
                    )
            return ControlResult.failure(
                message=f"No window found matching '{title}'",
                code="WINDOW_NOT_FOUND"
            )
        else:
            hwnd = win32gui.GetForegroundWindow()
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return ControlResult.success(message="Minimized current window")
    except Exception as e:
        return ControlResult.failure(
            message="Failed to minimize window",
            code="MINIMIZE_FAILED",
            error_message=str(e)
        )


def handle_maximize_window(title=None, **_):
    if not HAS_WIN32:
        return ControlResult.failure(
            message="win32gui not available",
            code="MISSING_DEPENDENCY"
        )
    try:
        if title:
            windows = _get_visible_windows()
            for w in windows:
                if title.lower() in w["title"].lower():
                    win32gui.ShowWindow(w["hwnd"], win32con.SW_MAXIMIZE)
                    return ControlResult.success(
                        message=f"Maximized window: {w['title']}"
                    )
            return ControlResult.failure(
                message=f"No window found matching '{title}'",
                code="WINDOW_NOT_FOUND"
            )
        else:
            hwnd = win32gui.GetForegroundWindow()
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return ControlResult.success(message="Maximized current window")
    except Exception as e:
        return ControlResult.failure(
            message="Failed to maximize window",
            code="MAXIMIZE_FAILED",
            error_message=str(e)
        )


def register_window_controls(registry):
    registry.register(
        ControlFunction(
            name="get_active_window",
            intent="get active window",
            description="Get the title of the currently active window",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            handler=handle_get_active_window
        ),
        extra_keywords=["active window", "current window", "what window", "foreground"]
    )
    registry.register(
        ControlFunction(
            name="list_windows",
            intent="list visible windows",
            description="List all visible window titles",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            handler=handle_list_windows
        ),
        extra_keywords=["visible windows", "all windows", "open windows"]
    )
    registry.register(
        ControlFunction(
            name="focus_window",
            intent="focus window by title",
            description="Bring a specific window to the foreground by title",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["title"],
            handler=handle_focus_window
        ),
        extra_keywords=["focus window", "bring to front", "switch to window"]
    )
    registry.register(
        ControlFunction(
            name="minimize_window",
            intent="minimize window",
            description="Minimize the current or specified window",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            optional_entities=["title"],
            handler=handle_minimize_window
        ),
        extra_keywords=["minimize", "hide window"]
    )
    registry.register(
        ControlFunction(
            name="maximize_window",
            intent="maximize window",
            description="Maximize the current or specified window",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            optional_entities=["title"],
            handler=handle_maximize_window
        ),
        extra_keywords=["maximize", "full screen window"]
    )
