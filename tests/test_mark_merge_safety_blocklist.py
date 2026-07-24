import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
BANNED_MODULES = {
    "actions.desktop",
    "actions.code_helper",
    "actions.dev_agent",
    "actions.send_message",
    "agent.executor",
    "agent.planner",
    "setup",
    "config.api_keys",
}

BANNED_PATTERNS = [
    "exec(",
    "eval(",
    "shell=True",
    'shell = "True"',
    "api_keys.json",
]

NEW_FILES = [
    "engine/ui_loader.py",
    "engine/ui_adapter.py",
    "engine/ui_event_bridge.py",
    "engine/tool_category_view.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _iter_py(root, suffix=".py"):
    for p in root.rglob(f"*{suffix}"):
        parts = p.parts
        if any(x in parts for x in (".venv", "__pycache__", ".pytest_cache", "data")):
            continue
        yield p


class TestMarkMergeSafetyBlocklist:
    def test_no_banned_imports(self):
        for search in BANNED_MODULES:
            found = []
            for py_file in _iter_py(ROOT / "engine"):
                text = _read(py_file)
                if f"import {search}" in text or f"from {search}" in text:
                    found.append(str(py_file.relative_to(ROOT)))
            assert not found, f"Banned import '{search}' found in: {found}"

    def test_no_banned_patterns(self):
        for fname in NEW_FILES:
            path = ROOT / fname
            if not path.exists():
                continue
            text = _read(path)
            for pat in BANNED_PATTERNS:
                assert pat not in text, f"Banned pattern '{pat}' found in {fname}"

    def test_no_new_shell_true(self):
        for fname in NEW_FILES:
            path = ROOT / fname
            if not path.exists():
                continue
            text = _read(path)
            assert "shell" not in text.lower() or "shell true" not in text.lower().replace("'", '"').replace('"', ""), \
                f"Potential shell=True in {fname}"

    def test_ui_adapter_no_direct_gemini(self):
        path = ROOT / "engine/ui_adapter.py"
        if not path.exists():
            return
        text = _read(path)
        assert "gemini_brain" not in text.lower(), "ui_adapter must not import gemini_brain"
        assert "groq_asr" not in text.lower(), "ui_adapter must not import groq_asr"
        assert "tool_registry" not in text.lower(), "ui_adapter must not import tool_registry directly"

    def test_ui_adapter_no_api_key_exposure(self):
        path = ROOT / "engine/ui_adapter.py"
        if not path.exists():
            return
        text = _read(path)
        assert "api_keys.json" not in text, "ui_adapter must not reference api_keys.json"
        assert "return os.getenv(" not in text, "ui_adapter get_env_status must return bools only"

    def test_www_mark_js_no_direct_tool_calls(self):
        js_path = ROOT / "www_mark"
        if not js_path.exists():
            return
        banned_js = ["eel.gemini", "eel.groq", "eel.tool_registry", "eel.local_skills",
                     "eel.gemini_brain", "eel.groq_asr", "eel.groq_intent"]
        for js_file in js_path.glob("*.js"):
            text = _read(js_file)
            for term in banned_js:
                assert term not in text.lower().replace(" ", ""), \
                    f"JS file {js_file.name} may call {term} directly"