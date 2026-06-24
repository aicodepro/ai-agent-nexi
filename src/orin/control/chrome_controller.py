import time

from src.orin.control.base import ControlResult, ControlFunction
from src.orin.control.browser_session import BrowserSession

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


def handle_open_chrome(url=None, **_):
    launched = BrowserSession.launch_chrome_process()
    if launched:
        time.sleep(1)
        if url:
            BrowserSession.navigate(url)
            return ControlResult.success(message=f"Chrome opened with URL: {url}")
        return ControlResult.success(message="Chrome opened")
    pw_ok = BrowserSession.ensure_running()
    if pw_ok:
        if url:
            BrowserSession.navigate(url)
            return ControlResult.success(message=f"Chrome opened with URL: {url}")
        return ControlResult.success(message="Chrome opened via Playwright")
    return ControlResult.failure(
        message="Could not launch Chrome",
        code="CHROME_LAUNCH_FAILED"
    )


def handle_open_url(url=None, **_):
    if not url:
        return ControlResult.failure(
            message="No URL specified",
            code="MISSING_ENTITY"
        )
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    launched = BrowserSession.launch_chrome_process()
    time.sleep(1)
    page = BrowserSession.navigate(url)
    if page:
        return ControlResult.success(
            message=f"Opened URL: {url}",
            data={"url": url}
        )
    try:
        import webbrowser
        webbrowser.open(url)
        return ControlResult.success(
            message=f"Opened URL via browser: {url}",
            data={"url": url}
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to open URL",
            code="URL_OPEN_FAILED",
            error_message=str(e)
        )


def handle_search_google(query=None, **_):
    if not query:
        return ControlResult.failure(
            message="No search query specified",
            code="MISSING_ENTITY"
        )
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    launched = BrowserSession.launch_chrome_process()
    time.sleep(1)
    page = BrowserSession.navigate(search_url)
    if page:
        return ControlResult.success(
            message=f"Searched Google for: {query}",
            data={"query": query, "url": search_url}
        )
    try:
        import webbrowser
        webbrowser.open(search_url)
        return ControlResult.success(
            message=f"Searched Google for: {query}",
            data={"query": query, "url": search_url}
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to search Google",
            code="SEARCH_FAILED",
            error_message=str(e)
        )


def handle_search_youtube(query=None, **_):
    if not query:
        return ControlResult.failure(
            message="No search query specified",
            code="MISSING_ENTITY"
        )
    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    launched = BrowserSession.launch_chrome_process()
    time.sleep(1)
    page = BrowserSession.navigate(search_url)
    if page:
        return ControlResult.success(
            message=f"Searched YouTube for: {query}",
            data={"query": query, "url": search_url}
        )
    try:
        import webbrowser
        webbrowser.open(search_url)
        return ControlResult.success(
            message=f"Searched YouTube for: {query}",
            data={"query": query, "url": search_url}
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to search YouTube",
            code="SEARCH_FAILED",
            error_message=str(e)
        )


def handle_open_youtube(**_):
    return handle_open_url(url="https://www.youtube.com")


def handle_new_tab(**_):
    page = BrowserSession.get_or_create_page(headless=False)
    if page:
        try:
            page.evaluate("window.open('about:blank', '_blank')")
            return ControlResult.success(message="Opened new tab")
        except Exception:
            pass
    if HAS_PYAUTOGUI:
        try:
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.5)
            return ControlResult.success(message="Opened new tab (keyboard)")
        except Exception:
            pass
    return ControlResult.success(message="New tab request sent")


def handle_close_tab(**_):
    page = BrowserSession.get_or_create_page(headless=False)
    if page:
        try:
            page.close()
            BrowserSession._page = None
            BrowserSession._page_connected = False
            return ControlResult.success(message="Closed current tab")
        except Exception:
            pass
    if HAS_PYAUTOGUI:
        try:
            pyautogui.hotkey("ctrl", "w")
            return ControlResult.success(message="Closed current tab (keyboard)")
        except Exception:
            pass
    return ControlResult.success(message="Tab close request sent")


def handle_get_tab_info(**_):
    page = BrowserSession.get_or_create_page(headless=False)
    if page:
        try:
            title = page.title()
            url = page.url
            return ControlResult.success(
                message=f"Current tab: {title}",
                data={"title": title, "url": url}
            )
        except Exception:
            pass
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
