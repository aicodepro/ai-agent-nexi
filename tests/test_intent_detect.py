"""NEXI understands a build request without a magic phrase.

Darsh: "I will not issue 'studio mode'. Nexi should interpret the request through its
own self-understanding." Today the grammar only matches "let's build X" / "studio mode: X",
so "I want a python function that reverses a string" is missed entirely.

Two invariants this must never break:
  * an 11-stage build must NOT start from a passing remark — inferred intent is CONFIRMED,
    only an explicit trigger runs straight through;
  * routine control ("open chrome") and questions ("how do I build a react app") must
    never be read as build requests.

Authorization is untouched: this changes what counts as a build REQUEST, never who may
authorize one.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.studio import intent_detect as det


# ---- explicit triggers run straight through --------------------------------------

@pytest.mark.parametrize("text", [
    "let's build a python function that reverses a string",
    "lets build me a dashboard",
    "studio mode: build a REST api",
    "Nexi, start building a cli tool",
])
def test_explicit_triggers_are_recognised_immediately(text):
    d = det.detect(text)
    assert d["action"] == "build"
    assert d["explicit"] is True
    assert d["confidence"] == 1.0


# ---- natural phrasing is UNDERSTOOD, then confirmed -------------------------------

@pytest.mark.parametrize("text", [
    "I want a python function that reverses a string",
    "can you make me a tool that renames files",
    "I need a dashboard that shows revenue",
    "create a REST api for orders",
    "could you write a script that backs up my photos",
    "please implement a login system",
])
def test_natural_build_requests_are_understood(text):
    d = det.detect(text)
    assert d["action"] == "confirm", f"missed build intent in {text!r}: {d}"
    assert d["goal"], "no goal extracted"
    assert d["explicit"] is False


def test_inferred_intent_is_never_started_without_confirming():
    """The safety line: understanding is not permission to spend 11 stages."""
    d = det.detect("I want a python function that reverses a string")
    assert d["action"] != "build", "an inferred request must be confirmed, not auto-started"


def test_confirmation_question_names_the_goal():
    d = det.detect("I need a dashboard that shows revenue")
    q = det.confirmation_question(d)
    assert "dashboard" in q and "?" in q


# ---- things that merely LOOK like builds ------------------------------------------

@pytest.mark.parametrize("text", [
    "open chrome", "close the window", "play music", "screenshot",
    "what time is it", "search for python tutorials", "read my email",
    "remind me to call mum", "translate this to french",
])
def test_routine_commands_never_trigger_a_build(text):
    assert det.detect(text)["action"] == "ignore", f"{text!r} would have started a build"


@pytest.mark.parametrize("text", [
    "how do I build a react app",
    "what is a closure in python",
    "explain how docker works",
    "which is better, flask or fastapi",
])
def test_questions_about_building_are_not_build_requests(text):
    """Asking ABOUT building wants an answer, not a team."""
    assert det.detect(text)["action"] == "ignore", f"{text!r} was read as a build request"


def test_empty_input_is_ignored():
    assert det.detect("")["action"] == "ignore"
    assert det.detect("   ")["action"] == "ignore"


# ---- goal extraction --------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("I want a python function that reverses a string", "reverses a string"),
    ("can you make me a tool that renames files", "renames files"),
    ("let's build a project regarding a dashboard", "dashboard"),
])
def test_goal_strips_the_request_scaffolding(text, expected):
    assert expected in det.detect(text)["goal"]


def test_threshold_boundary_is_not_lost_to_float_error():
    """REGRESSION: 0.35 + 0.10 is 0.4499999... in float, so a raw `>= 0.45`
    silently rejected a request scoring exactly the threshold."""
    d = det.detect("I need a dashboard that shows revenue")
    assert d["confidence"] >= 0.45
    assert d["action"] == "confirm"


# ---- opencode user-config passthrough ---------------------------------------------

def test_opencode_isolation_is_the_default():
    """Without the opt-in, the injected roster still replaces the user's setup."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "agent_runtime" / "adapters.py").read_text(
        encoding="utf-8", errors="replace")
    assert '"tools": {"*": False}' in src
    assert "NEXI_OPENCODE_USE_USER_CONFIG" in src


def test_opencode_passthrough_keeps_external_directory_denied():
    """Opting in must widen the toolbox, never the filesystem boundary."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "agent_runtime" / "adapters.py").read_text(
        encoding="utf-8", errors="replace")
    block = src[src.index("NEXI_OPENCODE_USE_USER_CONFIG"):]
    block = block[:block.index("OPENCODE_CONFIG_CONTENT")]
    assert 'config.pop("mcp"' in block and 'config.pop("plugin"' in block
    # Strip comments before asserting — a comment mentioning the boundary is not code
    # touching it, and matching prose would make this test lie in both directions.
    code = "\n".join(ln.split("#", 1)[0] for ln in block.splitlines())
    assert "external_directory" not in code, "opt-in must not touch the directory boundary"
    assert 'config.pop("permission"' not in code, "permission block must survive the opt-in"
