#!/usr/bin/env python3
"""Playwright validation for Mark UI canonical state flow."""

from __future__ import annotations

import pathlib
import sys


def _fail(message: str) -> None:
    print(f"FAIL playwright {message}")
    raise SystemExit(1)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright, expect
    except Exception as exc:  # pragma: no cover
        print(f"FAIL playwright import reason={type(exc).__name__}")
        return 1

    root = pathlib.Path(__file__).resolve().parents[1]
    index = root / "www_mark" / "index.html"
    if not index.exists():
        print(f"FAIL playwright missing index={index}")
        return 1

    eel_mock = """
    window.eel = {
      expose: function() {},
      ui_get_env_status: function() { return function(cb) { if (cb) cb({groq:false, gemini:false, openrouter:false}); }; },
      ui_get_runtime_status: function() { return function(cb) { if (cb) cb({wake_enabled:true, active_workflow:false}); }; },
      ui_submit_text: function() { return function(cb) { if (cb) cb({ok:true}); }; },
      ui_submit_file_drop: function() { return function(cb) { if (cb) cb({ok:true, files:[]}); }; },
      wakeJarvisFromUi: function() { return function(cb) { if (cb) cb({ok:true}); }; },
      toggleJarvisSleepWake: function() { return function(cb) { if (cb) cb({ok:true}); }; }
    };
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.add_init_script(eel_mock)
        page.goto(index.as_uri(), wait_until="load")

        state = page.locator("#jarvis-state")
        log = page.locator("#jarvis-log")
        expect(state).to_have_text("SLEEP MODE")
        print("PASS playwright initial sleep")

        def emit(state_name: str, source: str = "system", text: str = "", log_message: str = "", log_level: str = "sys", label: str = "") -> None:
            payload = {"state": state_name, "source": source, "text": text}
            if log_message:
                payload["log"] = log_message
                payload["log_level"] = log_level
            if label:
                payload["label"] = label
                payload["message"] = label
            page.evaluate("payload => window.updateJarvisState(payload)", payload)

        def text(selector: str) -> str:
            return page.locator(selector).inner_text(timeout=3000)

        def log_text() -> str:
            return log.inner_text(timeout=3000)

        # Hotword flow
        emit("wake_detected", "hotword", log_message="WAKE: Hotword detected", log_level="wake", label="HOTWORD DETECTED")
        expect(state).to_have_text("HOTWORD DETECTED")
        emit("listening", "hotword", log_message="SYS: Listening...")
        expect(state).to_have_text("LISTENING")
        emit("recognising", "asr", log_message="SYS: Recognising speech...")
        expect(state).to_have_text("RECOGNISING")
        page.evaluate("text => window.senderText(text)", "open notepad")
        _assert("You: open notepad" in log_text(), "transcript log missing")
        emit("thinking", "assistant", log_message="SYS: Thinking...")
        expect(state).to_have_text("THINKING")
        page.evaluate("text => window.receiverText(text)", "Opening Notepad.")
        _assert("JARVIS: Opening Notepad." in log_text(), "assistant response missing")
        emit("saying", "tts", log_message="SYS: Saying...")
        expect(state).to_have_text("SAYING")
        emit("sleep", "system", log_message="SYS: Sleep mode")
        expect(state).to_have_text("SLEEP MODE")
        print("PASS playwright hotword flow")

        # Double clap flow
        emit("wake_detected", "double_clap", log_message="WAKE: Double clap detected", log_level="wake", label="DOUBLE CLAP DETECTED")
        expect(state).to_have_text("DOUBLE CLAP DETECTED")
        emit("listening", "double_clap", log_message="SYS: Listening...")
        expect(state).to_have_text("LISTENING")
        emit("recognising", "asr", log_message="SYS: Recognising speech...")
        expect(state).to_have_text("RECOGNISING")
        emit("thinking", "assistant", log_message="SYS: Thinking...")
        expect(state).to_have_text("THINKING")
        emit("saying", "tts", log_message="SYS: Saying...")
        expect(state).to_have_text("SAYING")
        emit("sleep", "system", log_message="SYS: Sleep mode")
        expect(state).to_have_text("SLEEP MODE")
        print("PASS playwright double clap flow")
        print("PASS playwright recognising/thinking/saying")

        logs = log_text()
        for required in (
            "WAKE: Hotword detected",
            "WAKE: Double clap detected",
            "SYS: Listening...",
            "SYS: Recognising speech...",
            "SYS: Thinking...",
            "SYS: Saying...",
            "SYS: Sleep mode",
        ):
            _assert(required in logs, f"missing active log {required}")
        print("PASS playwright active logs")

        before = log_text().count("SYS: Listening...")
        emit("listening", "double_clap", log_message="SYS: Listening...")
        emit("listening", "double_clap", log_message="SYS: Listening...")
        after = log_text().count("SYS: Listening...")
        _assert(after - before <= 1, "duplicate listening log spam")
        emit("saying", "tts", log_message="SYS: Saying...")
        expect(state).to_have_text("SAYING")
        emit("sleep", "system", log_message="SYS: Sleep mode")
        expect(state).to_have_text("SLEEP MODE")
        _assert(text("#jarvis-state") == "SLEEP MODE", "stale listening after sleep")
        print("PASS playwright no duplicate states")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
