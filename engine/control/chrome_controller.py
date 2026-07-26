import threading
import webbrowser
from urllib.parse import urlencode

from engine.control.base import ControlResult, ControlFunction
from engine.control.browser_session import BrowserSession

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except Exception:
    HAS_PYAUTOGUI = False


def _open_with_default_browser(url, timeout=5.0):
    result = {"ok": False, "error": "Default browser did not accept the URL"}

    def open_url():
        try:
            result["ok"] = bool(webbrowser.open(url))
        except Exception as exc:
            result["error"] = str(exc)

    thread = threading.Thread(target=open_url, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return False, "Default browser launch timed out"
    return result["ok"], result["error"]


def _normalise_url(url):
    return url if url.startswith(("http://", "https://")) else "https://" + url


def _open_url(url):
    if BrowserSession.navigate(url):
        return True, ""
    if BrowserSession.launch_chrome_process(url):
        return True, ""
    opened, error = _open_with_default_browser(url)
    if opened:
        return True, ""
    return False, error or BrowserSession.get_last_error()


def handle_open_chrome(url=None, **_):
    if url:
        url = _normalise_url(url)
        if BrowserSession.navigate(url) or BrowserSession.launch_chrome_process(url):
            return ControlResult.success(message=f"Chrome opened with URL: {url}")
    elif BrowserSession.launch_chrome_process() or BrowserSession.ensure_running():
        return ControlResult.success(message="Chrome opened")
    return ControlResult.failure(
        message="Could not launch Chrome",
        code="CHROME_LAUNCH_FAILED",
        error_message=BrowserSession.get_last_error(),
    )


def handle_open_url(url=None, **_):
    if not url:
        return ControlResult.failure(
            message="No URL specified",
            code="MISSING_ENTITY"
        )
    url = _normalise_url(url)
    opened, error = _open_url(url)
    if opened:
        return ControlResult.success(
            message=f"Opened URL: {url}",
            data={"url": url}
        )
    return ControlResult.failure(
        message="Failed to open URL",
        code="URL_OPEN_FAILED",
        error_message=error or BrowserSession.get_last_error(),
    )


def handle_search_google(query=None, **_):
    if not query:
        return ControlResult.failure(
            message="No search query specified",
            code="MISSING_ENTITY"
        )
    search_url = "https://www.google.com/search?" + urlencode({"q": query})
    opened, error = _open_url(search_url)
    if opened:
        return ControlResult.success(
            message=f"Searched Google for: {query}",
            data={"query": query, "url": search_url}
        )
    return ControlResult.failure(
        message="Failed to search Google",
        code="SEARCH_FAILED",
        error_message=error or BrowserSession.get_last_error(),
    )


def handle_search_youtube(query=None, **_):
    if not query:
        return ControlResult.failure(
            message="No search query specified",
            code="MISSING_ENTITY"
        )
    search_url = "https://www.youtube.com/results?" + urlencode({"search_query": query})
    opened, error = _open_url(search_url)
    if opened:
        return ControlResult.success(
            message=f"Searched YouTube for: {query}",
            data={"query": query, "url": search_url}
        )
    return ControlResult.failure(
        message="Failed to search YouTube",
        code="SEARCH_FAILED",
        error_message=error or BrowserSession.get_last_error(),
    )


def handle_open_youtube(**_):
    return handle_open_url(url="https://www.youtube.com")


def handle_new_tab(**_):
    if BrowserSession.new_page():
        return ControlResult.success(message="Opened new tab")
    if HAS_PYAUTOGUI:
        try:
            pyautogui.hotkey("ctrl", "t")
            return ControlResult.success(message="Opened new tab (keyboard)")
        except Exception as exc:
            return ControlResult.failure(
                message="Failed to open new tab",
                code="NEW_TAB_FAILED",
                error_message=str(exc),
            )
    return ControlResult.failure(
        message="Failed to open new tab",
        code="NEW_TAB_FAILED",
        error_message=BrowserSession.get_last_error(),
    )


def handle_close_tab(**_):
    if BrowserSession.close_current_page():
        return ControlResult.success(message="Closed current tab")
    if HAS_PYAUTOGUI:
        try:
            pyautogui.hotkey("ctrl", "w")
            return ControlResult.success(message="Closed current tab (keyboard)")
        except Exception as exc:
            return ControlResult.failure(
                message="Failed to close current tab",
                code="CLOSE_TAB_FAILED",
                error_message=str(exc),
            )
    return ControlResult.failure(
        message="Failed to close current tab",
        code="CLOSE_TAB_FAILED",
        error_message=BrowserSession.get_last_error(),
    )


def handle_get_tab_info(**_):
    info = BrowserSession.get_tab_info()
    if info:
        return ControlResult.success(
            message=f"Current tab: {info['title']}",
            data=info,
        )
    title = BrowserSession.get_active_title()
    if title:
        return ControlResult.success(
            message=f"Active window: {title}",
            data={"title": title}
        )
    return ControlResult.failure(
        message="Could not get tab info",
        code="TAB_INFO_FAILED"
    )


def register_chrome_controls(registry):
    registry.register(
        ControlFunction(
            name="open_chrome",
            intent="open Chrome browser",
            description="Open Google Chrome browser",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            optional_entities=["url"],
            handler=handle_open_chrome
        ),
        extra_keywords=["chrome", "browser", "google chrome"]
    )
    registry.register(
        ControlFunction(
            name="open_url",
            intent="open URL",
            description="Open a specific URL in Chrome",
            risk_level="MEDIUM",
            privacy_sensitivity="MEDIUM",
            requires_confirmation=False,
            required_entities=["url"],
            handler=handle_open_url
        ),
        extra_keywords=["go to", "navigate to", "open link", "take me to"]
    )
    registry.register(
        ControlFunction(
            name="search_google",
            intent="search Google",
            description="Search Google for a query",
            risk_level="MEDIUM",
            privacy_sensitivity="MEDIUM",
            requires_confirmation=False,
            required_entities=["query"],
            handler=handle_search_google
        ),
        extra_keywords=["google", "search web", "search google", "look up"]
    )
    registry.register(
        ControlFunction(
            name="search_youtube",
            intent="search YouTube",
            description="Search YouTube for a query",
            risk_level="MEDIUM",
            privacy_sensitivity="MEDIUM",
            requires_confirmation=False,
            required_entities=["query"],
            handler=handle_search_youtube
        ),
        extra_keywords=["youtube", "search youtube", "you tube"]
    )
    registry.register(
        ControlFunction(
            name="open_youtube",
            intent="open YouTube",
            description="Open YouTube website",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            handler=handle_open_youtube
        ),
        extra_keywords=["open youtube", "go to youtube", "launch youtube"]
    )
    registry.register(
        ControlFunction(
            name="new_tab",
            intent="open new tab",
            description="Open a new browser tab",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            handler=handle_new_tab
        ),
        extra_keywords=["new tab", "create tab"]
    )
    registry.register(
        ControlFunction(
            name="close_tab",
            intent="close current tab",
            description="Close the current browser tab",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            handler=handle_close_tab
        ),
        extra_keywords=["close tab", "close this tab"]
    )
    registry.register(
        ControlFunction(
            name="get_tab_info",
            intent="get active tab info",
            description="Get the title and URL of the active browser tab",
            risk_level="SAFE",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            handler=handle_get_tab_info
        ),
        extra_keywords=["tab info", "current tab", "what tab", "tab title", "tab url"]
    )
