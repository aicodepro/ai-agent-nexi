"""Verify that www_mark/controller.js exposes all required Eel functions."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_JS = ROOT / "www_mark" / "controller.js"

REQUIRED_EXPOSES = [
    "updateJarvisState",
    "updateState",
    "senderText",
    "receiverText",
    "appendLog",
    "appendResponse",
    "DisplayMessage",
    "ShowHood",
    "setStatus",
    "updateSpeechCapsule",
    "hideSpeechCapsule",
    "setContextIndicator",
    "displayControlResult",
    "showEmergencyStop",
    "showOutputWorkspace",
    "closeOutputWorkspace",
    "minimizeOutputWorkspace",
    "pinOutputWorkspace",
]

REQUIRED_HANDLERS = [
    # State handling
    "updateJarvisState",
    "senderText",
    "receiverText",
    # Compat wrappers
    "updateState",
    "appendLog",
    "appendResponse",
    "addLogEntry",
]

REQUIRED_STATES = [
    "online",
    "idle",
    "wake_detected",
    "hotword_detected",
    "double_clap_detected",
    "clap_detected",
    "listening_started",
    "listening",
    "speech_started",
    "speech_ended",
    "asr_started",
    "asr_result",
    "transcribing",
    "thinking",
    "command_started",
    "speaking",
    "tts_started",
    "tts_done",
    "sleeping",
    "error",
]


class TestMarkUIEelExposedFunctions:

    def test_file_exists(self):
        assert CONTROLLER_JS.exists(), f"{CONTROLLER_JS} not found"

    def test_all_required_exposes_present(self):
        content = CONTROLLER_JS.read_text(encoding="utf-8")
        exposed = set()
        for m in re.finditer(r'eel\.expose\([^,]+,\s*["\']([^"\']+)["\']', content):
            exposed.add(m.group(1))
        for name in REQUIRED_EXPOSES:
            assert name in exposed, f"Missing eel.expose for {name!r}"

    def test_all_function_definitions_present(self):
        content = CONTROLLER_JS.read_text(encoding="utf-8")
        lines = content.splitlines()
        for name in REQUIRED_HANDLERS:
            found = any(
                re.search(rf'window\.{re.escape(name)}\s*=', line)
                or re.search(rf'function\s+{re.escape(name)}\s*\(', line)
                for line in lines
            )
            assert found, f"Function {name!r} not defined in controller.js"

    def test_all_required_states_handled(self):
        content = CONTROLLER_JS.read_text(encoding="utf-8")
        for state in REQUIRED_STATES:
            assert state in content, f"State {state!r} not referenced in controller.js"


class TestMarkUIMainJS:

    def test_main_js_exists(self):
        main = ROOT / "www_mark" / "main.js"
        assert main.exists()

    def test_submit_calls_ui_submit_text(self):
        main = ROOT / "www_mark" / "main.js"
        content = main.read_text(encoding="utf-8")
        assert "eel.ui_submit_text" in content, "main.js must call eel.ui_submit_text"
        assert "window.senderText" in content, "main.js must call senderText before submit"

    def test_init_logs_online(self):
        main = ROOT / "www_mark" / "main.js"
        content = main.read_text(encoding="utf-8")
        assert "online" in content.lower() or "ONLINE" in content, "init should log ONLINE"


class TestMarkUISafety:

    def test_no_direct_tool_execution(self):
        """JS should not call tools, subprocess, or expose secrets directly."""
        content = CONTROLLER_JS.read_text(encoding="utf-8")
        forbidden = ["exec(", "spawn(", "shell:", "subprocess", "GEMINI_API_KEY", "GROQ_API_KEY"]
        for f in forbidden:
            assert f not in content, f"Forbidden pattern {f!r} found in controller.js"