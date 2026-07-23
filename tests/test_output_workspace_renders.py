"""Long output must actually reach the user.

engine/command.py's show_workspace branch REPLACES what Nexi displays and speaks with a
short summary (main_ui_text / spoken_text), on the assumption the full body renders in the
output workspace. The old www/ UI had a draggable workspace panel; www_mark/ does not, and
the handler was left as `window.showOutputWorkspace = function () {};`. So the body was
dropped on the floor: the user heard "here's the summary" and saw nothing, and "show it
again" did nothing either.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "www_mark" / "controller.js"

pytestmark = pytest.mark.skipif(not CONTROLLER.exists(), reason="www_mark UI not present")


def _body_of(fn: str) -> str:
    src = CONTROLLER.read_text(encoding="utf-8")
    match = re.search(rf"window\.{fn}\s*=\s*function\s*\([^)]*\)\s*\{{(.*?)\n  \}};", src, re.S)
    assert match, f"{fn} not found in controller.js"
    return match.group(1)


def test_show_output_workspace_is_not_a_no_op():
    body = _body_of("showOutputWorkspace")
    stripped = re.sub(r"//.*", "", body).strip()
    assert stripped, "showOutputWorkspace is a no-op — routed output is silently discarded"


def test_show_output_workspace_renders_the_content():
    body = _body_of("showOutputWorkspace")
    assert "workspace_content" in body, "handler ignores the content Python sends"
    assert "appendChild" in body, "must append; innerHTML += is the known DOM-thrash bug"
    assert "textContent" in body, "use textContent so content is never parsed as markup"


def test_python_still_sends_workspace_content():
    """If this key is ever renamed, the JS above goes silently blank again."""
    command = (ROOT / "engine" / "command.py").read_text(encoding="utf-8")
    assert "workspace_content" in command
