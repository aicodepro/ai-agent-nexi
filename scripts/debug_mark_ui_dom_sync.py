#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "www_mark" / "index.html"

STATES = [
    ("sleep", "SLEEPING", "mark_ui_sleeping_sync"),
    ("online", "ONLINE", "mark_ui_online_sync"),
    ("listening", "LISTENING", "mark_ui_listening_sync"),
    ("recognising", "RECOGNISING", "mark_ui_recognising_sync"),
    ("thinking", "THINKING", "mark_ui_thinking_sync"),
    ("saying", "SAYING", "mark_ui_saying_sync"),
]

TARGETS = [
    "nexi-state",
    "nexi-center-state",
    "nexi-bottom-state",
    "nexi-status-badge",
    "nexi-mode",
    "nexi-orb-state",
]


def _pass(name: str) -> None:
    print(f"PASS {name}")


def _fail(name: str, detail: str) -> None:
    print(f"FAIL {name} blocker={detail}")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _fail("mark_ui_dom_all_state_targets_sync", f"playwright_import:{type(exc).__name__}")
        return 1

    if not INDEX.exists():
        _fail("mark_ui_dom_all_state_targets_sync", "www_mark/index.html_missing")
        return 1

    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script(
            """
            window.__nexiAcks = [];
            window.eel = {
              expose: function () {},
              ui_state_ack: function (sessionId, state, label) {
                window.__nexiAcks.push({ sessionId: sessionId, state: state, label: label });
              }
            };
            """
        )
        page.goto(INDEX.as_uri(), wait_until="domcontentloaded")
        page.wait_for_function("() => typeof window.nexiApplyState === 'function'")

        for state, label, check_name in STATES:
            page.evaluate(
                "([state, label]) => window.nexiApplyState({ state, label, source: 'debug', session_id: 'debug-session' })",
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
            _pass("mark_ui_all_targets_match")
        else:
            failures += 1
            _fail("mark_ui_all_targets_match", values)

        ack_count = page.evaluate("() => window.__nexiAcks.length")
        if ack_count >= len(STATES):
            _pass("ui_ack_received")
        else:
            failures += 1
            _fail("ui_ack_received", f"ack_count={ack_count}")

        browser.close()

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
