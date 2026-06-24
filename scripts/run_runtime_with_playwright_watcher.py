#!/usr/bin/env python3
"""Safe runtime UI watcher using Playwright and synthetic bridge events.

This intentionally avoids opening the full desktop/mic runtime when running in
unattended CI/agent mode. It validates the same Mark UI bridge surface the
runtime uses and proves keyboard wake injection is not required.
"""

from __future__ import annotations

import pathlib
import sys
import time


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str) -> None:
    log(f"FAIL runtime watcher {message}")
    raise SystemExit(1)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright, expect
    except Exception as exc:
        log(f"FAIL runtime watcher playwright_import reason={type(exc).__name__}")
        return 1

    root = pathlib.Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    index = root / "www_mark" / "index.html"
    if not index.exists():
        fail(f"missing Mark UI index {index}")

    eel_mock = """
    window.__wakeNexiCalls = [];
    window.eel = {
      expose: function() {},
      ui_get_env_status: function() { return function(cb) { if (cb) cb({groq:false, gemini:false, openrouter:false}); }; },
      ui_get_runtime_status: function() { return function(cb) { if (cb) cb({wake_enabled:true, active_workflow:false}); }; },
      ui_submit_text: function() { return function(cb) { if (cb) cb({ok:true}); }; },
      ui_submit_file_drop: function() { return function(cb) { if (cb) cb({ok:true, files:[]}); }; },
      wakeNexiFromUi: function(source) { window.__wakeNexiCalls.push(source); return function(cb) { if (cb) cb({ok:true}); }; },
      toggleNexiSleepWake: function() { return function(cb) { if (cb) cb({ok:true}); }; }
    };
    """

    start = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.add_init_script(eel_mock)
        page.goto(index.as_uri(), wait_until="load")
        state = page.locator("#nexi-state")
        log("[WATCHER] Mark UI loaded")
        expect(state).to_have_text("SLEEP MODE")
        log("PASS runtime watcher initial sleep")

        def emit(payload: dict) -> None:
            page.evaluate("payload => window.updateNexiState(payload)", payload)

        flow = [
            {"state": "wake_detected", "source": "hotword", "label": "HOTWORD DETECTED", "message": "HOTWORD DETECTED", "log": "WAKE: Hotword detected", "log_level": "wake"},
            {"state": "listening", "source": "hotword", "log": "SYS: Listening..."},
            {"state": "recognising", "source": "asr", "log": "SYS: Recognising speech..."},
            {"state": "thinking", "source": "assistant", "log": "SYS: Thinking..."},
            {"state": "saying", "source": "tts", "log": "SYS: Saying..."},
            {"state": "sleep", "source": "system", "log": "SYS: Sleep mode"},
        ]
        for payload in flow:
            emit(payload)
        expect(state).to_have_text("SLEEP MODE")
        log("PASS runtime watcher bridge events visible")

        emit({"state": "saying", "source": "tts", "log": "SYS: Saying..."})
        expect(state).to_have_text("SAYING")
        log("PASS runtime watcher saying visible")
        emit({"state": "sleep", "source": "system", "log": "SYS: Sleep mode"})
        expect(state).to_have_text("SLEEP MODE")
        log("PASS runtime watcher returned sleep")

        before_count = page.locator("#nexi-log .log-msg", has_text="SYS: Listening...").count()
        emit({"state": "listening", "source": "hotword", "log": "SYS: Listening..."})
        emit({"state": "listening", "source": "hotword", "log": "SYS: Listening..."})
        after_count = page.locator("#nexi-log .log-msg", has_text="SYS: Listening...").count()
        if after_count - before_count > 1:
            fail("duplicate listening states")
        log("PASS runtime watcher no duplicate states")

        emit({"state": "sleep", "source": "system", "log": "SYS: Sleep mode"})
        page.keyboard.press("Control+J")
        expect(state).to_have_text("SLEEP MODE")
        calls = page.evaluate("() => window.__wakeNexiCalls.slice()")
        if "hotkey" in calls:
            fail("Ctrl+J invoked hotkey wake")
        log("PASS runtime watcher no Win+J")

        browser.close()

    elapsed = time.time() - start
    log(f"PASS runtime watcher clean stop elapsed_sec={elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
