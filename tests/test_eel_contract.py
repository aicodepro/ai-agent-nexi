import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


ROOT = Path(__file__).resolve().parents[1]
JS_ROOT = ROOT / "www_mark"
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


_JS_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


def _strip_js_comments(text: str) -> str:
    # Comments (e.g. studio_panel.js's header documenting `eel.studioEvent(payload)` as
    # the Python->JS call it wires up) contain literal `eel.X(` text that isn't a real
    # call. Strip comments first so the static scan only sees actual code.
    return _JS_COMMENT_RE.sub("", text)


def _js_calls_python():
    calls = set()
    for path in _iter_files(JS_ROOT, ".js"):
        text = _strip_js_comments(_read(path))
        for match in re.finditer(r"eel\.(\w+)\s*\(", text):
            name = match.group(1)
            if name != "expose":
                calls.add(name)
    return calls


def _js_exposes():
    exposes = set()
    for path in _iter_files(JS_ROOT, ".js"):
        text = _strip_js_comments(_read(path))
        # This codebase always exposes as eel.expose(fnRef, 'name') (two args), not the
        # bare eel.expose(name) form, so match both.
        for match in re.finditer(r"eel\.expose\(\s*[\w.]+\s*,\s*[\"'](\w+)[\"']\s*\)", text):
            exposes.add(match.group(1))
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
    assert "toggleNexiSleepWake" in _python_exposes()
    assert "wakeNexiFromUi" in _python_exposes()


def test_ui_has_sleeping_and_listening_states():
    controller = _read(JS_ROOT / "controller.js")
    index = _read(JS_ROOT / "index.html")
    main_js = _read(JS_ROOT / "main.js")
    assert "sleeping" in controller
    assert "listening" in controller
    # Sleep/wake control is now id="power-button" (title "Sleep / Wake"), wired to
    # eel.toggleNexiSleepWake(), rather than an element literally named SleepWakeBtn.
    assert 'id="power-button"' in index
    assert "toggleNexiSleepWake" in main_js
