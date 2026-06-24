import os
import time


class BrowserSession:
    _playwright_available = False
    _browser = None
    _context = None
    _page = None
    _page_connected = False

    @classmethod
    def _check_playwright(cls):
        if not cls._playwright_available:
            try:
                from playwright.sync_api import sync_playwright
                cls._playwright_available = True
            except ImportError:
                cls._playwright_available = False
        return cls._playwright_available

    @classmethod
    def get_or_create_page(cls, headless=False):
        if cls._page and cls._page_connected:
            try:
                cls._page.title()
                return cls._page
            except Exception:
                cls._page_connected = False

        if not cls._check_playwright():
            return None

        try:
            from playwright.sync_api import sync_playwright
            if cls._browser is None:
                playwright = sync_playwright().start()
                cls._browser = playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                cls._context = cls._browser.new_context(
                    no_viewport=True,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                cls._page = cls._context.new_page()
                cls._page.goto("about:blank")
                cls._page_connected = True
            return cls._page
        except Exception:
            return None

    @classmethod
    def ensure_running(cls):
        page = cls.get_or_create_page(headless=False)
        if page is None:
            return False
        return True

    @classmethod
    def close(cls):
        try:
            if cls._page:
                cls._page.close()
            if cls._context:
                cls._context.close()
            if cls._browser:
                cls._browser.close()
        except Exception:
            pass
        finally:
            cls._page = None
            cls._context = None
            cls._browser = None
            cls._page_connected = False

    @classmethod
    def navigate(cls, url):
        page = cls.get_or_create_page(headless=False)
        if page is None:
            return None
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            return page
        except Exception:
            return None

    @classmethod
    def get_active_title(cls):
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return title
        except ImportError:
            return ""

    @classmethod
    def launch_chrome_process(cls):
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Users\marke\AppData\Local\Google\Chrome\Application\chrome.exe",
        ]
        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    os.system(f'start "" "{path}"')
                    time.sleep(1)
                    return True
                except Exception:
                    return False
        try:
            os.system("start chrome")
            time.sleep(1)
            return True
        except Exception:
            return False
