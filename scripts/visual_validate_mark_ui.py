"""Visual validation of Mark-style Eel UI using Playwright.
Opens www_mark/index.html directly, mocks Eel bridge, captures screenshots."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WWW_MARK = ROOT / "www_mark"
ARTIFACTS = ROOT / "artifacts" / "ui_mark_validation"


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[VISUAL] Playwright not installed. Skipping visual validation.")
        print("[VISUAL] Install: pip install playwright && playwright install chromium")
        return False

    index_html = WWW_MARK / "index.html"
    if not index_html.exists():
        print(f"[VISUAL] {index_html} not found")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        page = context.new_page()

        # Inject Eel mock before page loads
        page.add_init_script("""
            window.eel = {
                ui_submit_text: () => Promise.resolve({ok: true}),
                ui_submit_file_drop: () => Promise.resolve({ok: true, files: [], prompt: 'What should I do?'}),
                ui_get_env_status: () => Promise.resolve({groq: true, gemini: true, openrouter: false}),
                ui_get_runtime_status: () => Promise.resolve({state: 'idle', wake_enabled: true}),
                ui_get_capabilities: () => Promise.resolve({}),
                ui_get_tool_categories: () => Promise.resolve({}),
                ui_get_suggestions: () => Promise.resolve([]),
                allCommands: () => Promise.resolve(),
                toggleJarvisSleepWake: () => Promise.resolve(),
                wakeJarvisFromUi: () => Promise.resolve(),
            };
        """)

        page.goto(f"file:///{index_html.as_posix()}")
        page.wait_for_timeout(2000)

        sizes = {
            "mark_ui_1366x768": (1366, 768),
            "mark_ui_1920x1080": (1920, 1080),
        }
        for name, (w, h) in sizes.items():
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(500)
            path = ARTIFACTS / f"{name}.png"
            page.screenshot(path=path, full_page=False)
            print(f"[VISUAL] Screenshot saved: {path}")

        # State screenshots at 1920x1080
        page.set_viewport_size({"width": 1920, "height": 1080})
        states = ["idle", "listening", "thinking", "speaking"]
        for st in states:
            page.evaluate(f"if(window.setOrbState)window.setOrbState('{st}')")
            page.wait_for_timeout(800)
            path = ARTIFACTS / f"mark_ui_{st}.png"
            page.screenshot(path=path, full_page=False)
            print(f"[VISUAL] {st} screenshot saved: {path}")

        browser.close()

    print("[VISUAL] All screenshots captured successfully.")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)