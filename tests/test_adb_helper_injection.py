"""The adb helpers built shell strings from their arguments:

    os.system(f'adb shell input text "{message}"')

A message containing `" & calc & "` closed the quote and ran calc on THIS
machine, not the phone. Same class as engine/features.py openCommand.

Currently unused (nothing imports adbInput/keyEvent/tapEvents), so this is a
latent hole rather than a live one — fixed anyway so wiring the phone feature up
later can't reintroduce it.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import helper


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(helper.time, "sleep", lambda *_a: None)


PAYLOADS = [
    '" & calc & "',
    "hi\" && del /f /s /q C:\\* && echo \"",
    "hello | calc",
    "text > C:\\pwned.txt",
    "$(calc)",
    "`calc`",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_adb_input_never_builds_a_host_shell_string(payload):
    with patch("engine.helper.subprocess.run") as run:
        helper.adbInput(payload)

    run.assert_called_once()
    argv = run.call_args.args[0]
    # list form, not a string -> there is no host shell to inject into
    assert isinstance(argv, list), f"argv must be a list, got {type(argv).__name__}"
    assert argv[:4] == ["adb", "shell", "input", "text"]
    assert run.call_args.kwargs.get("shell") is not True
    # the payload must survive as ONE argument (quoted), never as extra argv entries
    assert len(argv) == 5, f"payload split into multiple args: {argv!r}"


def test_the_old_os_system_path_is_gone():
    """Regression: helper must not shell out at all anymore."""
    assert not hasattr(helper, "os"), "helper still imports os — os.system path may be back"


@pytest.mark.parametrize(
    "fn,args,expected",
    [
        (lambda: helper.keyEvent(4), None, ["adb", "shell", "input", "keyevent", "4"]),
        (lambda: helper.tapEvents(10, 20), None, ["adb", "shell", "input", "tap", "10", "20"]),
    ],
)
def test_the_helpers_still_do_their_job(fn, args, expected):
    with patch("engine.helper.subprocess.run") as run:
        fn()
    assert run.call_args.args[0] == expected


def test_a_normal_message_still_reaches_the_device():
    with patch("engine.helper.subprocess.run") as run:
        helper.adbInput("hello there")
    argv = run.call_args.args[0]
    # shlex.quote may wrap it, but the text must still be in there
    assert "hello there" in argv[4]
