"""The status badge must never contradict what NEXI is actually doing.

These tests used to read `www/index.html` and `www/controller.js`. The UI directory is
`www_mark/`, so every one of them died on FileNotFoundError and checked nothing. The old
element ids (`SourceBadge`, `ContextIndicator`) no longer exist either — the HUD was
rebuilt around `nexi-status-badge` + `nexi-bottom-state`.

They also matched exact source strings (`"saying: 'SAYING'"`), which breaks on any
reformat. The invariant that actually matters is the state -> label MAPPING: if any
TTS/speaking event resolved to `listening`, the HUD would read LISTENING while NEXI is
talking, and the user would speak into a mic that isn't open. So parse the maps and assert
the mapping.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "www_mark"
INDEX = WWW / "index.html"
CONTROLLER = WWW / "controller.js"

pytestmark = pytest.mark.skipif(not INDEX.exists(), reason="www_mark UI not present")


def _js_object(name: str) -> dict[str, str]:
    """Pull `var NAME = { key: 'value', ... }` out of controller.js."""
    src = CONTROLLER.read_text(encoding="utf-8")
    match = re.search(rf"var\s+{name}\s*=\s*\{{(.*?)\}}\s*;", src, re.S)
    assert match, f"{name} not found in controller.js"
    return dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", match.group(1)))


def test_exactly_one_status_badge_element():
    html = INDEX.read_text(encoding="utf-8")
    assert html.count('id="nexi-status-badge"') == 1
    assert html.count('id="nexi-bottom-state"') == 1


def test_speaking_never_renders_as_listening():
    """The bug this guards: HUD says LISTENING while TTS is playing."""
    states = _js_object("ALLOWED_STATES")
    labels = _js_object("STATE_LABELS")
    for event in ("saying", "speaking", "tts_started"):
        assert states[event] == "saying", f"{event} must resolve to the saying state"
        assert labels[states[event]] == "SAYING"


def test_listening_states_resolve_to_listening():
    states = _js_object("ALLOWED_STATES")
    for event in ("listening", "listening_started", "waiting_for_speech", "hearing_speech"):
        assert states[event] == "listening"


def test_idle_states_resolve_to_sleep():
    states = _js_object("ALLOWED_STATES")
    labels = _js_object("STATE_LABELS")
    for event in ("sleep", "idle", "sleeping", "tts_done"):
        assert states[event] == "sleep"
    assert labels["sleep"] == "SLEEPING"


def test_every_state_has_a_label():
    """An unmapped state renders `undefined` in the badge."""
    states = _js_object("ALLOWED_STATES")
    labels = _js_object("STATE_LABELS")
    missing = sorted(set(states.values()) - set(labels))
    assert not missing, f"states with no badge label: {missing}"


def test_every_state_has_an_orb_state():
    states = _js_object("ALLOWED_STATES")
    orbs = _js_object("ORB_STATES")
    missing = sorted(set(states.values()) - set(orbs))
    assert not missing, f"states the orb cannot render: {missing}"


def test_context_indicator_cannot_hijack_the_main_badge():
    """setContextIndicator is a no-op stub; if it ever writes the badge again, context
    text would overwrite the live state the badge exists to show."""
    src = CONTROLLER.read_text(encoding="utf-8")
    body = re.search(r"window\.setContextIndicator\s*=\s*function\s*\([^)]*\)\s*\{(.*?)\};", src, re.S)
    assert body, "setContextIndicator not found"
    assert "nexi-status-badge" not in body.group(1)


def test_markup_default_matches_the_sleep_label():
    """Static HTML ships a badge value; if it drifts from STATE_LABELS the first paint
    shows a label the JS would never produce."""
    html = INDEX.read_text(encoding="utf-8")
    sleep_label = _js_object("STATE_LABELS")["sleep"]
    assert f'id="nexi-status-badge" class="info-row nexi-state-sleep">{sleep_label}<' in html
