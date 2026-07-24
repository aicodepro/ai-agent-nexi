"""openCommand() fed raw voice text to cmd.exe.

    os.system('start ' + query)

query is whatever the ASR heard, routed through the intent args. "open notepad
& del /f /s /q C:\\*" ran BOTH halves — the launch AND the wipe. Voice -> shell,
no validation anywhere on the path (engine/command.py:1261 calls this live).

engine/control/process_controller.start_process() already does this exact launch
behind an allowlist, so openCommand now routes through it instead of building its
own shell string.

These assert on the shell call itself: openCommand's bare `except:` swallows
everything, so "it raised" proves nothing here.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class _NoRowsCursor:
    """DB lookup misses -> openCommand falls through to the launch path."""

    def execute(self, *_a, **_k):
        return None

    def fetchall(self):
        return []


@pytest.fixture
def features(monkeypatch):
    import engine.features as f

    monkeypatch.setattr(f, "cursor", _NoRowsCursor(), raising=False)
    monkeypatch.setattr(f, "speak", lambda *_a, **_k: None, raising=False)
    return f


# Each of these reaches cmd.exe as a second command if the query is not validated.
INJECTIONS = [
    "notepad & calc",
    "notepad && calc",
    "notepad | calc",
    "notepad > C:\\windows\\system32\\drivers\\etc\\hosts",
    "notepad & del /f /s /q C:\\*",
    "notepad ; calc",
    "notepad ^& calc",
    "notepad `calc`",
    "notepad %USERPROFILE%",
    'notepad" & calc & "',
]


@pytest.mark.parametrize("payload", INJECTIONS)
def test_injection_never_reaches_the_shell(features, monkeypatch, payload):
    # Patch os.system ITSELF, not one module's reference to it. Patching
    # process_controller.os.system would let the old features.os.system call run the
    # real injection AND record nothing, so the assert loop would pass over an empty
    # list — a vacuous test that executes the exploit it claims to catch.
    calls = []
    monkeypatch.setattr(os, "system", lambda cmd, *a, **k: calls.append(cmd) or 0)
    said = []
    monkeypatch.setattr(features, "speak", lambda msg="", *a, **k: said.append(str(msg)))

    features.openCommand("open " + payload)

    for cmd in calls:
        assert not any(c in cmd for c in "&|;><^`%\""), (
            f"shell metacharacter reached cmd.exe: {cmd!r}"
        )
    # Not vacuous: prove it was ACTIVELY rejected rather than silently doing nothing.
    assert any("not found" in s for s in said), (
        f"payload {payload!r} was neither launched nor rejected — "
        f"os.system calls={calls!r} speak={said!r}"
    )


def test_the_old_shell_string_is_gone(features):
    """Regression: features must not build its own 'start ' + query anymore."""
    with patch("engine.features.os.system") as direct_system:
        with patch("engine.control.process_controller.os.system"):
            features.openCommand("open notepad & calc")
    direct_system.assert_not_called()


def test_a_legitimate_app_still_launches(features):
    """The allowlist must not break the actual feature."""
    with patch("engine.control.process_controller.subprocess.Popen") as popen:
        features.openCommand("open notepad")

    popen.assert_called_once()
    assert popen.call_args.args[0] == ["notepad.exe"]
    assert popen.call_args.kwargs["shell"] is False
