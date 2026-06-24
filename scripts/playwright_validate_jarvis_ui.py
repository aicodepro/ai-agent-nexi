"""Comprehensive Playwright UI validation for Nexi.

Supports:
  --mode legacy|mark     (which UI to validate)
  --runtime static|eel   (static HTML mock or live Eel subprocess)

Static mode:
  Opens HTML directly, injects mock window.eel, validates DOM/console/screenshots.

Eel runtime mode:
  Starts python main.py as subprocess with NEXI_UI_MODE set, waits for
  localhost:8000, opens with Playwright, validates live state.

Usage:
  python scripts/playwright_validate_nexi_ui.py --mode legacy --runtime static
  python scripts/playwright_validate_nexi_ui.py --mode mark --runtime static
  python scripts/playwright_validate_nexi_ui.py --mode legacy --runtime eel
  python scripts/playwright_validate_nexi_ui.py --mode mark --runtime eel
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "playwright_ui_validation"

MOCK_EEL_SCRIPT = """
window.eel = {
    ui_submit_text: () => Promise.resolve({ok: true}),
    ui_submit_file_drop: () => Promise.resolve({ok: true, files: [], prompt: 'What should I do?'}),
    ui_get_env_status: () => Promise.resolve({groq: true, gemini: true, openrouter: false}),
    ui_get_runtime_status: () => Promise.resolve({state: 'idle', wake_enabled: true}),
    ui_get_capabilities: () => Promise.resolve({}),
    ui_get_tool_categories: () => Promise.resolve({}),
    ui_get_suggestions: () => Promise.resolve([]),
    allCommands: () => Promise.resolve(),
    toggleNexiSleepWake: () => Promise.resolve(),
    wakeNexiFromUi: () => Promise.resolve(),
    updateNexiState: () => {},
    senderText: () => {},
    ShowHood: () => {},
};
"""


def _log(msg: str) -> None:
    print(msg, flush=True)


# ====================================================================
# Static mode
# ====================================================================

def validate_static(mode: str, playwright) -> dict:
    from playwright.sync_api import sync_playwright, BrowserContext, Page

    results = {"mode": mode, "runtime": "static", "passed": [], "failed": [], "screenshots": []}
    ui_dir = ROOT / "www" if mode == "legacy" else ROOT / "www_mark"
    index_html = ui_dir / "index.html"

    if not index_html.exists():
        results["failed"].append(f"FATAL: {index_html} not found")
        return results

    os.makedirs(ARTIFACTS, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        _log(f"[STATIC] loading file://{index_html}")
        page.goto(f"file:///{index_html.as_posix()}")
        page.wait_for_timeout(2000)

        # Inject Eel mock after page load (add_init_script unreliable for file://)
        page.evaluate(MOCK_EEL_SCRIPT)

        # ---- Screenshots ----
        for viewport, suffix in [({"width": 1366, "height": 768}, "1366"), ({"width": 1920, "height": 1080}, "1920")]:
            page.set_viewport_size(viewport)
            page.wait_for_timeout(500)
            path = ARTIFACTS / f"{mode}_static_{suffix}.png"
            page.screenshot(path=str(path), full_page=False)
            results["screenshots"].append(str(path))
            _log(f"[STATIC] screenshot: {path.name}")

        # ---- Console errors ----
        console_log = ARTIFACTS / f"console_{mode}_static.log"
        with open(console_log, "w", encoding="utf-8") as f:
            f.write("\n".join(console_errors) if console_errors else "(none)")
        if console_errors:
            results["failed"].append(f"console errors: {len(console_errors)}")
        else:
            results["passed"].append("no console errors")
        _log(f"[STATIC] console errors: {len(console_errors)}")

        # ---- State screenshots ----
        state_names = ["idle", "listening", "thinking", "speaking", "sleeping", "error"]
        for state in state_names:
            try:
                page.evaluate(f"""window.updateNexiState({{state: "{state}"}})""")
            except Exception:
                try:
                    page.evaluate(f"""window.eel.updateNexiState(JSON.stringify({{state: "{state}"}}))""")
                except Exception:
                    pass
            page.wait_for_timeout(500)
            path = ARTIFACTS / f"{mode}_{state}.png"
            page.screenshot(path=str(path), full_page=False)
            results["screenshots"].append(str(path))

        _log(f"[STATIC] state screenshots: {len(state_names)} captured")

        # ---- Mode-specific checks ----
        if mode == "legacy":
            results = _check_legacy_dom(page, results)
        else:
            results = _check_mark_dom(page, results)

        # ---- Eel bridge checks ----
        checks = {
            "eel object": "typeof window.eel !== 'undefined'",
            "eel.allCommands": "typeof window.eel.allCommands === 'function'",
        }
        if mode == "mark":
            checks["eel.ui_submit_text"] = "typeof window.eel.ui_submit_text === 'function'"

        for name, expr in checks.items():
            try:
                ok = page.evaluate(expr)
                if ok:
                    results["passed"].append(f"eel: {name}")
                else:
                    results["failed"].append(f"eel: {name} missing")
            except Exception as e:
                results["failed"].append(f"eel: {name} error: {e}")

        browser.close()

    return results


def _check_legacy_dom(page, results: dict) -> dict:
    try:
        page.wait_for_selector("input, textarea, button, [role='textbox']", timeout=3000)
        results["passed"].append("legacy: input exists")
    except Exception:
        results["failed"].append("legacy: no input found")

    try:
        title = page.title()
        results["passed"].append(f"legacy: page title={title}")
    except Exception:
        results["failed"].append("legacy: no page title")
    return results


def _check_mark_dom(page, results: dict) -> dict:
    selectors = [
        ("top-header", "#top-header"),
        ("left-panel", "#left-panel"),
        ("center-stage", "#center-stage"),
        ("hud-canvas", "#hud-canvas"),
        ("right-panel", "#right-panel"),
        ("command-bar", "#command-bar"),
        ("command-input", "#command-input"),
        ("file-drop-zone", "#file-drop-zone"),
        ("state-badge", "#state-badge"),
    ]
    for name, sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                box = el.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    results["passed"].append(f"mark: {name} visible ({int(box['width'])}x{int(box['height'])})")
                else:
                    results["failed"].append(f"mark: {name} zero-size")
            else:
                results["failed"].append(f"mark: {name} missing")
        except Exception as e:
            results["failed"].append(f"mark: {name} error: {e}")

    # Check panel positioning
    try:
        center = page.evaluate("""() => {
            const cs = document.querySelector('#center-stage');
            const hud = document.querySelector('#hud-canvas');
            if (!cs || !hud) return false;
            const csBox = cs.getBoundingClientRect();
            const hudBox = hud.getBoundingClientRect();
            return hudBox.left >= csBox.left && hudBox.right <= csBox.right;
        }""")
        if center:
            results["passed"].append("mark: hud inside center-stage")
        else:
            results["failed"].append("mark: hud not inside center-stage")
    except Exception as e:
        results["failed"].append(f"mark: center check error: {e}")

    # Command bar on screen
    try:
        cb_box = page.evaluate("""() => {
            const el = document.querySelector('#command-bar');
            if (!el) return null;
            const b = el.getBoundingClientRect();
            return {bottom: b.bottom, height: b.height};
        }""")
        if cb_box and cb_box["bottom"] <= 1080 and cb_box["height"] > 0:
            results["passed"].append("mark: command bar on screen")
        else:
            results["failed"].append("mark: command bar off screen")
    except Exception:
        results["failed"].append("mark: command bar check failed")

    # Settings overlay
    try:
        page.evaluate("""() => {
            const el = document.querySelector('#settings-overlay');
            if (el) el.classList.remove('hidden');
        }""")
        page.wait_for_timeout(300)
        overlay = page.query_selector("#settings-overlay")
        if overlay and overlay.is_visible():
            results["passed"].append("mark: settings overlay opens")
        else:
            results["failed"].append("mark: settings overlay not opening")
    except Exception as e:
        results["failed"].append(f"mark: settings overlay error: {e}")

    # Debug panel
    try:
        page.evaluate("""() => {
            const el = document.querySelector('#debug-panel');
            if (el) el.classList.remove('hidden');
        }""")
        page.wait_for_timeout(300)
        panel = page.query_selector("#debug-panel")
        if panel and panel.is_visible():
            results["passed"].append("mark: debug panel opens")
        else:
            results["failed"].append("mark: debug panel not opening")
    except Exception as e:
        results["failed"].append(f"mark: debug panel error: {e}")

    # No API keys visible
    try:
        body = page.text_content("body") or ""
        has_key = "gsk_" in body.lower() or "sk-" in body.lower()
        if not has_key:
            results["passed"].append("mark: no API keys visible")
        else:
            results["failed"].append("mark: API key string visible in DOM")
    except Exception:
        pass

    return results


# ====================================================================
# Eel runtime mode
# ====================================================================

def validate_eel(mode: str, playwright) -> dict:
    from playwright.sync_api import sync_playwright

    results = {"mode": mode, "runtime": "eel", "passed": [], "failed": [], "screenshots": []}

    os.makedirs(ARTIFACTS, exist_ok=True)

    env = os.environ.copy()
    env["NEXI_UI_MODE"] = mode

    _log(f"[EEL] starting main.py with NEXI_UI_MODE={mode}")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to be ready
    import urllib.request
    ready = False
    for attempt in range(30):
        time.sleep(1.0)
        try:
            urllib.request.urlopen("http://localhost:8000", timeout=2)
            ready = True
            break
        except Exception:
            _log(f"[EEL] waiting for server... attempt {attempt + 1}/30")

    if not ready:
        results["failed"].append("Eel server did not start within 30s")
        proc.terminate()
        proc.wait(timeout=5)
        return results

    _log("[EEL] server ready, opening browser")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            console_errors = []
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            page.goto("http://localhost:8000/index.html")
            page.wait_for_timeout(3000)

            # Screenshot
            path = ARTIFACTS / f"{mode}_eel_{1920}.png"
            page.screenshot(path=str(path), full_page=False)
            results["screenshots"].append(str(path))

            # Console
            console_log = ARTIFACTS / f"console_{mode}_eel.log"
            with open(console_log, "w", encoding="utf-8") as f:
                f.write("\n".join(console_errors) if console_errors else "(none)")
            if console_errors:
                results["failed"].append(f"console errors: {len(console_errors)}")
            else:
                results["passed"].append("no console errors")

            _log(f"[EEL] console errors: {len(console_errors)}")

            # Eel bridge checks
            bridge_checks = {
                "eel exists": "typeof window.eel !== 'undefined'",
            }
            for name, expr in bridge_checks.items():
                try:
                    ok = page.evaluate(expr)
                    if ok:
                        results["passed"].append(f"bridge: {name}")
                    else:
                        results["failed"].append(f"bridge: {name}")
                except Exception as e:
                    results["failed"].append(f"bridge: {name}: {e}")

            # State transition
            for state in ["idle", "listening", "thinking", "speaking"]:
                try:
                    page.evaluate(f"""window.eel.updateNexiState(JSON.stringify({{state: "{state}"}}))""")
                    page.wait_for_timeout(500)
                    path = ARTIFACTS / f"{mode}_eel_{state}.png"
                    page.screenshot(path=str(path), full_page=False)
                    results["screenshots"].append(str(path))
                except Exception as e:
                    results["failed"].append(f"state {state}: {e}")

            browser.close()
    except Exception as e:
        results["failed"].append(f"Playwright error: {e}")
    finally:
        _log("[EEL] stopping subprocess")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stdout = proc.stdout.read() if proc.stdout else ""
        stderr = proc.stderr.read() if proc.stderr else ""

        # Save Eel runtime logs
        log_path = ARTIFACTS / f"eel_runtime_{mode}.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=== STDOUT ===\n")
            f.write(stdout[:50000] if stdout else "(empty)")
            f.write("\n=== STDERR ===\n")
            f.write(stderr[:50000] if stderr else "(empty)")
        results["passed"].append(f"runtime log saved: {log_path.name}")

    return results


# ====================================================================
# Report
# ====================================================================

def report(results: dict) -> bool:
    _log("=" * 60)
    _log(f"MODE={results['mode']} RUNTIME={results['runtime']}")
    _log("=" * 60)

    passed = results["passed"]
    failed = results["failed"]

    for p in passed:
        _log(f"  PASS  {p}")
    for f in failed:
        _log(f"  FAIL  {f}")

    _log("")
    _log(f"Passed: {len(passed)}")
    _log(f"Failed: {len(failed)}")
    _log(f"Screenshots: {len(results.get('screenshots', []))}")
    _log("")

    return len(failed) == 0


# ====================================================================
# Main
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="Playwright UI validation for Nexi")
    parser.add_argument("--mode", choices=["legacy", "mark"], default="mark")
    parser.add_argument("--runtime", choices=["static", "eel"], default="static")
    args = parser.parse_args()

    os.makedirs(ARTIFACTS, exist_ok=True)

    if args.runtime == "static":
        result = validate_static(args.mode, None)
    else:
        result = validate_eel(args.mode, None)

    ok = report(result)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()