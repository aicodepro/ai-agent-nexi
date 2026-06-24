import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


ROOT = Path(__file__).resolve().parents[1]
JS_ROOT = ROOT / "www"
PY_ROOTS = [ROOT / "engine", ROOT / "src", ROOT / "main.py"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _iter_files(root, suffix):
    if root.is_file():
        if root.suffix == suffix:
            yield root
        return
    for path in root.rglob(f"*{suffix}"):
        if ".venv" not in path.parts and "__pycache__" not in path.parts:
            yield path


def _js_calls_python():
    calls = set()
    for path in _iter_files(JS_ROOT, ".js"):
        text = _read(path)
        for match in re.finditer(r"eel\.(\w+)\s*\(", text):
            name = match.group(1)
            if name != "expose":
                calls.add(name)
    return calls


def _js_exposes():
    exposes = set()
    for path in _iter_files(JS_ROOT, ".js"):
        text = _read(path)
        for match in re.finditer(r"eel\.expose\(\s*(\w+)\s*\)", text):
            exposes.add(match.group(1))
    return exposes


def _python_exposes():
    exposes = set()
    for root in PY_ROOTS:
        for path in _iter_files(root, ".py"):
            text = _read(path)
            for match in re.finditer(r"@eel\.expose\s*\n\s*def\s+(\w+)", text):
                exposes.add(match.group(1))
    return exposes


def _python_calls_js():
    calls = set()
    ignored = {"expose", "init", "start", "spawn"}
    for root in PY_ROOTS:
        for path in _iter_files(root, ".py"):
            text = _read(path)
            for match in re.finditer(r"eel\.(\w+)\s*\(", text):
                name = match.group(1)
                if name not in ignored:
                    calls.add(name)
            for match in re.finditer(r"(?:safe_eel_call|_safe_eel_call)\(\s*[\"'](\w+)[\"']", text):
                calls.add(match.group(1))
    return calls


def test_js_python_exposed_functions_exist():
    missing = _js_calls_python() - _python_exposes()
    assert missing == set()


def test_python_js_called_functions_defined_or_guarded():
    missing = _python_calls_js() - _js_exposes()
    assert missing == set()


def test_wake_button_function_exists():
    assert "toggleJarvisSleepWake" in _python_exposes()
    assert "wakeJarvisFromUi" in _python_exposes()


def test_ui_has_sleeping_and_listening_states():
    controller = _read(JS_ROOT / "controller.js")
    index = _read(JS_ROOT / "index.html")
    assert "sleeping" in controller
    assert "listening" in controller
    assert "SleepWakeBtn" in index
