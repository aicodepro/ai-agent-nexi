#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "www_mark" / "index.html"
MAIN_PY = ROOT / "main.py"
COMMAND_PY = ROOT / "engine" / "command.py"

STATES = [
    ("sleep", "SLEEPING", "ui_dom_sleeping"),
    ("online", "ONLINE", "ui_dom_online"),
    ("listening", "LISTENING", "ui_dom_listening"),
    ("recognising", "RECOGNISING", "ui_dom_recognising"),
    ("thinking", "THINKING", "ui_dom_thinking"),
    ("saying", "SAYING", "ui_dom_saying"),
]

TARGETS = [
    "jarvis-state",
    "jarvis-center-state",
    "jarvis-bottom-state",
    "jarvis-status-badge",
    "jarvis-mode",
    "jarvis-orb-state",
]


def _pass(name: str) -> None:
    print(f"PASS {name}")


def _fail(name: str, detail: str) -> None:
    print(f"FAIL {name} blocker={detail}")


def check_static() -> list[str]:
    failures = []

    # PASS eel_js_loaded
    if INDEX.exists():
        html = INDEX.read_text(encoding="utf-8")
        if '/eel.js' in html and 'src="/eel.js"' in html:
            _pass("eel_js_loaded")
        else:
            failures.append("eel_js_loaded")
            _fail("eel_js_loaded", "www_mark/index.html missing /eel.js script tag")
    else:
        failures.append("eel_js_loaded")
        _fail("eel_js_loaded", "www_mark/index.html not found")

    # PASS python_ack_exposed
    source_py = None
    source_label = ""
    if COMMAND_PY.exists():
        source_py = COMMAND_PY.read_text(encoding="utf-8")
        source_label = "engine/command.py"
    elif MAIN_PY.exists():
        source_py = MAIN_PY.read_text(encoding="utf-8")
        source_label = "main.py"
    if source_py is not None:
        if "@eel.expose" in source_py and "def ui_state_ack" in source_py:
            _pass(f"python_ack_exposed ({source_label})")
        else:
            failures.append("python_ack_exposed")
            _fail("python_ack_exposed", f"{source_label} missing @eel.expose ui_state_ack")
    else:
        failures.append("python_ack_exposed")
        _fail("python_ack_exposed", "neither main.py nor engine/command.py found")

    return failures


def main() -> int:
    static_fails = check_static()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _fail("all_ui_state_targets_match", f"playwright_import:{type(exc).__name__}")
        return 1

    if not INDEX.exists():
        return 1

    failures = len(static_fails)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script(
            """
            window.__jarvisAcks = [];
            window.eel = {
              expose: function () {},
              ui_state_ack: function (sessionId, state, label) {
                window.__jarvisAcks.push({ sessionId: sessionId, state: state, label: label });
                return Promise.resolve({ ok: true });
              }
            };
            """
        )
        page.goto(INDEX.as_uri(), wait_until="domcontentloaded")
        page.wait_for_function("() => typeof window.jarvisApplyState === 'function'")

        # PASS jarvisApplyState_exposed
        _pass("jarvisApplyState_exposed")

        for state, label, check_name in STATES:
            page.evaluate(
                "([state, label]) => window.jarvisApplyState({ state, label, source: 'debug', session_id: 'debug-session' })",
                [state, label],
            )
            values = page.evaluate(
                "targets => Object.fromEntries(targets.map(id => [id, (document.getElementById(id) || {}).textContent || '']))",
                TARGETS,
            )
            mismatches = {key: value for key, value in values.items() if value.strip() != label}
            if mismatches:
                failures += 1
                _fail(check_name, f"mismatches={mismatches}")
            else:
                _pass(check_name)

        values = page.evaluate(
            "targets => targets.map(id => (document.getElementById(id) || {}).textContent || '').join('|')",
            TARGETS,
        )
        if len(set(values.split("|"))) == 1:
            _pass("all_ui_state_targets_match")
        else:
            failures += 1
            _fail("all_ui_state_targets_match", values)

        ack_count = page.evaluate("() => window.__jarvisAcks.length")
        ack_session_count = page.evaluate("() => window.__jarvisAcks.filter(a => a.sessionId === 'debug-session').length")
        if ack_count >= len(STATES) and ack_session_count >= len(STATES):
            _pass("ui_ack_received")
        else:
            failures += 1
            _fail("ui_ack_received", f"ack_count={ack_count} session_ack_count={ack_session_count}")

        browser.close()

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
