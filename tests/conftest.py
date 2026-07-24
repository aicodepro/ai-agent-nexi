import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Snapshot os.environ as early as possible -- conftest.py loads before pytest
# collects (imports) any test module in this directory. Several engine modules
# (engine/command.py, engine/groq_asr.py, ...) call dotenv.load_dotenv() at
# THEIR OWN import time, which writes the repo's real .env straight into
# os.environ with no fixture/teardown to undo it. If any collected test file
# imports one of those modules at module level (e.g. test_no_cloud_before_wake.py
# imports engine.groq_asr), the pollution happens during collection -- before
# the first test's autouse fixtures ever run. Capturing the snapshot here,
# before collection, is what lets _isolate_os_environ() below restore a truly
# clean baseline for every test regardless of when/how the leak happened.
_PRISTINE_ENVIRON = dict(os.environ)

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




# ── Probe-cache isolation ───────────────────────────────────────────────────────
# agent_runtime caches CLI/model probe results in module-level dicts that nothing ever
# resets, so a test that populates them leaks into every later test in the process and
# results depend on file ORDER: test_model_policy::test_openrouter_chain_is_free_models_only
# passes alone but fails after test_cli_capabilities/test_model_discovery. Order-dependent
# failures look exactly like real regressions and cost real time to chase.
#
# Done as a hook, NOT an autouse fixture: an extra autouse fixture changes fixture
# finalization order across the whole suite, which broke monkeypatch teardown in ~77 tests
# (KeyError: 'PYTEST_CURRENT_TEST'). A hook does the same clearing without participating in
# fixture ordering at all.
def pytest_runtest_setup(item):
    os.environ.clear()
    os.environ.update(_PRISTINE_ENVIRON)
    for mod_name, attr in (
        ("engine.agent_runtime.cli_capabilities", "_CACHE"),
        ("engine.agent_runtime.model_discovery", "_CACHE"),
        ("engine.agent_runtime.model_ranking", "_CACHE"),
    ):
        mod = sys.modules.get(mod_name)
        cache = getattr(mod, attr, None) if mod else None
        if isinstance(cache, dict):
            cache.clear()
    health = sys.modules.get("engine.agent_runtime.model_health")
    if health is not None and hasattr(health, "_LOADED"):
        health._LOADED = False


# ── os.environ isolation ─────────────────────────────────────────────────────
# engine/command.py, engine/groq_asr.py etc. call dotenv.load_dotenv() at import
# time, writing the repo's real .env (personal mic-tuned DSP/clap thresholds,
# backend order, silence timeouts) straight into os.environ with no teardown.
# Whichever test (or test module import at COLLECTION time -- see
# _PRISTINE_ENVIRON above) triggers that first permanently pollutes the rest of
# the session for every later test expecting the code's own built-in defaults.
# Reset in pytest_runtest_setup (before the test body/its fixtures run) and
# again here (after teardown) so pollution from either direction never leaks
# across tests. Hook-based for the same reason as the probe-cache clearing above.
def pytest_runtest_teardown(item, nextitem):
    os.environ.clear()
    os.environ.update(_PRISTINE_ENVIRON)


import pytest


@pytest.fixture(scope="session")
def shared_playwright():
    """One sync_playwright() per session, shared by every browser-UI test file.

    Two separate hazards are handled here:
    1. Playwright's sync API can't be started twice across modules in one process
       ("Sync API inside the asyncio loop") - so we start it once and share it.
    2. An earlier test (test_chrome_controller) leaves a *running* asyncio loop
       registered on the main thread and never stops it; Playwright's sync API
       then refuses to start. The running-loop flag is thread-local, so clearing
       it here is safe and only affects this (the main) thread.
    """
    import asyncio
    if asyncio.events._get_running_loop() is not None:
        asyncio.events._set_running_loop(None)
    pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    with pw.sync_playwright() as p:
        yield p
