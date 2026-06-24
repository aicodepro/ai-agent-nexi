from src.orin.diagnostics.runtime_doctor import RuntimeDoctor, _check, run_all_checks


class PlaywrightDoctor:
    @classmethod
    def check(cls):
        results = run_all_checks()
        for r in results:
            if r["name"] == "Playwright":
                return r
        return {"name": "Playwright", "ok": False, "problem": "Playwright check not available"}

    @classmethod
    def is_available(cls):
        try:
            from playwright.sync_api import sync_playwright
            return True
        except ImportError:
            return False

    @classmethod
    def can_launch(cls):
        if not cls.is_available():
            return False, "Playwright not installed"
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            return True, ""
        except Exception as e:
            return False, str(e)
