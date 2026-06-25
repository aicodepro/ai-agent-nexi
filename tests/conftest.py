import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# ── Chrome-safety: neutralize desktop effectors for the whole test session ──────
# engine/features.py, command.py, chrome_controller.py fire pyautogui Ctrl+W / Alt+F4 and
# `taskkill /im chrome.exe`. When a test executes a browser/close/media tool live, those hit
# the user's focused window and CLOSE CHROME. Patch the effectors once at import so no test
# can drive the real keyboard/mouse or kill a process. Non-kill subprocess calls (netsh, etc.)
# pass through. A test that wants to assert a keystroke patches its own (runs later).


def _noop(*_a, **_k):
    return None


for _modname, _fns in (
    ("pyautogui", ("hotkey", "press", "keyDown", "keyUp", "typewrite", "write", "click", "doubleClick", "moveTo")),
    ("keyboard", ("press_and_release", "send", "write", "press", "release")),
):
    try:
        _mod = __import__(_modname)
        for _fn in _fns:
            if hasattr(_mod, _fn):
                setattr(_mod, _fn, _noop)
    except Exception:
        pass


def _is_kill(args) -> bool:
    cmd = args if isinstance(args, str) else " ".join(str(x) for x in (args or []))
    return "taskkill" in cmd.lower()


_real_system = os.system
os.system = lambda cmd, *a, **k: 0 if _is_kill(cmd) else _real_system(cmd, *a, **k)

for _fn in ("run", "call", "check_call", "check_output", "Popen"):
    _real = getattr(subprocess, _fn, None)
    if _real is None:
        continue

    def _make(real_fn):
        def guarded(args, *a, **k):
            if _is_kill(args):
                return subprocess.CompletedProcess(args, 0, "", "")
            return real_fn(args, *a, **k)
        return guarded

    setattr(subprocess, _fn, _make(_real))
