#!/usr/bin/env python
"""Verify Playwright can launch Chrome and navigate to a page."""
import sys
import os
import argparse
import time
import json

parser = argparse.ArgumentParser(description="Playwright runtime check")
parser.add_argument("--port", type=int, default=8765, help="Port to check")
parser.add_argument("--auto-close", action="store_true", help="Auto-close browser after check")
args = parser.parse_args()

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS: {name}")
        PASS += 1
    else:
        print(f"  FAIL: {name} - {detail}")
        FAIL += 1


def _launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception:
        return playwright.chromium.launch(channel="msedge", headless=True)


def _safe_error(error):
    return str(error).encode("ascii", "backslashreplace").decode("ascii")


def main():
    global PASS, FAIL
    print("=" * 60)
    print("PLAYWRIGHT RUNTIME CHECK")
    print("=" * 60)

    print("\n[1] Playwright Import")
    if args.port:
        print(f"  Port: {args.port}")
    if args.auto_close:
        print("  Auto-close: enabled")

    try:
        from playwright.sync_api import sync_playwright
        print("  PASS: playwright.sync_api imported")
        PASS += 1
    except ImportError as e:
        print(f"  FAIL: playwright.sync_api import failed - {e}")
        FAIL += 1
        return 1

    print("\n[2] Chrome Launch")
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto("about:blank")
            check("Chrome launched in headless mode", True)
            check("Page loaded about:blank", page.url == "about:blank")
            page.close()
            browser.close()
    except Exception as e:
        print(f"  FAIL: Chrome launch failed - {_safe_error(e)}")
        FAIL += 1

    print("\n[3] Navigation Test")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto("data:text/html,<h1>Hello</h1>", wait_until="domcontentloaded")
            title = page.title()
            check("Page loads data URL", True)
            browser.close()
    except Exception as e:
        print(f"  FAIL: Navigation failed - {_safe_error(e)}")
        FAIL += 1

    print("\n[4] Control Layer Integration")
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from engine.control import execute_control_action, list_control_actions
        actions = list_control_actions()
        action_names = [a["name"] for a in actions]

        check("Control layer has actions registered", len(actions) > 0)
        check("open_url action registered", "open_url" in action_names)
        check("search_google action registered", "search_google" in action_names)
        check("search_youtube action registered", "search_youtube" in action_names)
    except ImportError as e:
        print(f" FAIL: Control layer import failed - {e}")
        FAIL += 1

    print("\n[5] Intent Brain (Phase 2)")
    try:
        from engine.brain import IntentBrain
        brain = IntentBrain()

        r = brain.process("chrome kholo")
        check("chrome kholo maps to open Chrome intent",
              r.get("intent", "") in ("control_open_chrome", "control_open_chrome_hi"))

        r = brain.process("open you tube")
        check("open you tube maps to YouTube intent",
              r.get("intent", "") in ("control_open_youtube", "control_open_youtube_hi", "youtube"))

        r = brain.process("search youtube for AI tools")
        check("search youtube for AI tools maps to search YouTube",
              r.get("intent", "") in ("control_search_youtube", "control_search_youtube_hi"))

        r = brain.process("diagnose jarvi")
        check("diagnose jarvi maps to diagnostics intent",
              r.get("intent", "") == "diagnose_jarvi")

        r = brain.process("stop everything")
        check("stop everything maps to emergency stop",
              r.get("intent", "") in ("control_emergency_stop", "control_emergency_stop_hi"))
    except ImportError as e:
        print(f" FAIL: Intent brain import failed - {e}")
        FAIL += 1

    print("\n[6] Voice Response Layer (Phase 2)")
    try:
        from engine.voice import compose_response, compose_error
        r = compose_response({
            "function": "open_chrome",
            "risk_level": "MEDIUM",
            "requires_confirmation": False,
            "user_facing_summary": "Opening Chrome.",
            "language": "en",
            "missing_fields": [],
        })
        check("Voice response composes for open Chrome", "Chrome" in r or "chrome" in r.lower())

        r = compose_error("Something went wrong")
        check("Voice error response composes", len(r) > 0)
    except ImportError as e:
        print(f" FAIL: Voice layer import failed - {e}")
        FAIL += 1

    print("\n[7] Runtime Doctor (Phase 2)")
    try:
        from engine.diagnostic_doctors import diagnose, format_diagnosis
        result = diagnose()
        check("Runtime doctor runs diagnose", "ok" in result)
        report = format_diagnosis(result)
        check("Runtime doctor produces report", "Nexi Diagnostics" in report)
    except ImportError as e:
        print(f" FAIL: Diagnostics import failed - {e}")
        FAIL += 1

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")

    if args.auto_close:
        print("\nAuto-close: Script will exit now.")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
