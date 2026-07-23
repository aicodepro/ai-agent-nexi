import os
import shutil
import subprocess
import threading


class BrowserSession:
    _playwright_available = False
    _playwright = None
    _browser = None
    _context = None
    _page = None
    _page_connected = False
    _last_error = ""
    _lock = threading.RLock()

    @classmethod
    def _check_playwright(cls):
        if not cls._playwright_available:
            try:
                from playwright.sync_api import sync_playwright  # noqa: F401
                cls._playwright_available = True
            except ImportError:
                cls._playwright_available = False
        return cls._playwright_available

    @classmethod
    def _session_is_healthy(cls):
        try:
            return bool(
                cls._browser
                and cls._browser.is_connected()
                and cls._context
                and not cls._context.is_closed()
            )
        except Exception:
            return False

    @classmethod
    def _page_is_healthy(cls):
        try:
            return bool(cls._page and cls._page_connected and not cls._page.is_closed())
        except Exception:
            return False

    @classmethod
    def get_or_create_page(cls, headless=False):
        with cls._lock:
            if cls._page_is_healthy():
                return cls._page

            if cls._session_is_healthy():
                try:
                    cls._page = cls._context.new_page()
                    cls._page.goto("about:blank")
                    cls._page_connected = True
                    cls._last_error = ""
                    return cls._page
                except Exception as exc:
                    cls._last_error = f"Failed to create browser page: {exc}"
                    cls._close_locked(preserve_error=True)
                    return None

            cls._close_locked(preserve_error=True)
            if not cls._check_playwright():
                cls._last_error = "Playwright is not installed"
                return None

            try:
                from playwright.sync_api import sync_playwright

                cls._playwright = sync_playwright().start()
                cls._browser = cls._playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                cls._context = cls._browser.new_context(
                    no_viewport=True,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                cls._page = cls._context.new_page()
                cls._page.goto("about:blank")
                cls._page_connected = True
                cls._last_error = ""
                return cls._page
            except Exception as exc:
                cls._last_error = f"Playwright startup failed: {exc}"
                cls._close_locked(preserve_error=True)
                return None

    @classmethod
    def ensure_running(cls):
        return cls.get_or_create_page(headless=False) is not None

    @classmethod
    def _close_locked(cls, preserve_error=False):
        error = cls._last_error if preserve_error else ""
        for resource in (cls._page, cls._context, cls._browser):
            if resource:
                try:
                    resource.close()
                except Exception as exc:
                    if not error:
                        error = f"Browser cleanup failed: {exc}"
        if cls._playwright:
            try:
                cls._playwright.stop()
            except Exception as exc:
                if not error:
                    error = f"Playwright cleanup failed: {exc}"
        cls._page = None
        cls._context = None
        cls._browser = None
        cls._playwright = None
        cls._page_connected = False
        cls._last_error = error

    @classmethod
    def close(cls):
        with cls._lock:
            cls._close_locked()

    @classmethod
    def navigate(cls, url):
        with cls._lock:
            page = cls.get_or_create_page(headless=False)
            if page is None:
                return None
            try:
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
                cls._last_error = ""
                return page
            except Exception as exc:
                cls._last_error = f"Navigation failed: {exc}"
                return None

    @classmethod
    def new_page(cls):
        with cls._lock:
            if cls.get_or_create_page(headless=False) is None:
                return None
            try:
                cls._page = cls._context.new_page()
                cls._page.goto("about:blank")
                cls._page_connected = True
                cls._last_error = ""
                return cls._page
            except Exception as exc:
                cls._last_error = f"New tab failed: {exc}"
                return None

    @classmethod
    def close_current_page(cls):
        with cls._lock:
            if not cls._page_is_healthy():
                cls._last_error = "No managed browser tab is open"
                return False
            try:
                cls._page.close()
                cls._page = None
                cls._page_connected = False
                cls._last_error = ""
                return True
            except Exception as exc:
                cls._last_error = f"Close tab failed: {exc}"
                return False

    @classmethod
    def get_tab_info(cls):
        with cls._lock:
            page = cls.get_or_create_page(headless=False)
            if page is None:
                return None
            try:
                return {"title": page.title(), "url": page.url}
            except Exception as exc:
                cls._last_error = f"Tab info failed: {exc}"
                return None

    @classmethod
    def get_active_title(cls):
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(hwnd)
        except (ImportError, OSError):
            return ""

    @classmethod
    def get_last_error(cls):
        with cls._lock:
            return cls._last_error

    @classmethod
    def launch_chrome_process(cls, url=None):
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        candidates = [path for path in chrome_paths if os.path.exists(path)]
        path_chrome = shutil.which("chrome")
        if path_chrome:
            candidates.append(path_chrome)
        if not candidates:
            cls._last_error = "Chrome executable was not found"
            return False
        for path in candidates:
            try:
                args = [path]
                if url:
                    args.append(url)
                subprocess.Popen(
                    args,
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                cls._last_error = ""
                return True
            except Exception as exc:
                cls._last_error = f"Chrome launch failed: {exc}"
        return False
