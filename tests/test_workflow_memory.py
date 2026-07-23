"""NEXI learns reusable procedures from its own VERIFIED runs (#65 AWM + #70 + #66).

The property that keeps this from becoming a compounding-error machine: only a run
whose gates all passed may become procedure. A self-learning loop that admits its own
unverified output is precisely how agents reward-hack themselves — measured at 73.8%
in the DGM paper (docs/NEXI_AUTONOMY_IDEAS.md #82). So "success" here is never
self-reported; it comes from the governance gates.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.memory import workflow_memory as wm


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXI_WORKFLOW_MEMORY_PATH", str(tmp_path / "wf.json"))
    wm._MEM = None
    wm.reset()
    yield
    wm._MEM = None


TASK = "add a login form to the web app"
STEPS = ["read the router", "add the form component", "run the tests"]


# ---- outcome gating: the core safety property ------------------------------------

def test_unverified_runs_never_become_procedure():
    wm.record_run(TASK, ["guessed at it"], verified=False, outcome="tests failed")
    assert wm.recall(TASK) is None, "unverified work must never be recalled as procedure"


def test_a_failed_run_cannot_overwrite_a_working_procedure():
    for _ in range(2):
        wm.record_run(TASK, STEPS, verified=True)
    wm.record_run(TASK, ["something broken"], verified=False, outcome="crashed")
    entry = wm.recall(TASK)
    assert entry is not None and entry["steps"] == STEPS, "failure clobbered a good procedure"


def test_one_success_is_not_yet_trusted():
    """A single success can be luck — require repetition before it is advice."""
    wm.record_run(TASK, STEPS, verified=True)
    assert wm.recall(TASK) is None


def test_two_verified_runs_become_trusted():
    for _ in range(2):
        wm.record_run(TASK, STEPS, verified=True)
    entry = wm.recall(TASK)
    assert entry is not None
    assert entry["steps"] == STEPS
    assert entry["successes"] == 2


# ---- deprecation: memory that only grows, rots (#66) ------------------------------

def test_a_procedure_that_stops_working_is_retired():
    for _ in range(2):
        wm.record_run(TASK, STEPS, verified=True)
    assert wm.recall(TASK) is not None
    for _ in range(6):
        wm.record_run(TASK, [], verified=False, outcome="broke")
    assert wm.recall(TASK) is None, "a collapsed procedure must be retired, not replayed"
    assert wm.stats()["retired"] == 1


def test_failure_lessons_are_kept_for_the_next_attempt():
    wm.record_run(TASK, [], verified=False, outcome="missing auth middleware")
    for _ in range(2):
        wm.record_run(TASK, STEPS, verified=True)
    text = wm.guidance(TASK)
    assert "procedure that worked" in text
    assert "missing auth middleware" in text


# ---- retrieval ------------------------------------------------------------------

def test_phrasing_variants_reach_the_same_procedure():
    for _ in range(2):
        wm.record_run(TASK, STEPS, verified=True)
    assert wm.recall("please add the login form to my web app") is not None
    assert wm.recall("Add LOGIN form to web app") is not None


def test_unrelated_tasks_do_not_collide():
    for _ in range(2):
        wm.record_run(TASK, STEPS, verified=True)
    assert wm.recall("deploy the database migration to production") is None


def test_guidance_is_empty_when_nothing_is_learned():
    assert wm.guidance("a task never attempted") == ""


def test_corrupt_memory_file_does_not_crash(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("NEXI_WORKFLOW_MEMORY_PATH", str(bad))
    wm._MEM = None
    with pytest.warns(RuntimeWarning, match="quarantined"):
        assert wm.recall(TASK) is None      # degrades, never raises
    assert not bad.exists()
    assert len(list(tmp_path.glob("bad.json.corrupt-*"))) == 1
    assert wm.last_load_error()


# ---- studio wiring ---------------------------------------------------------------

def test_studio_only_learns_from_fully_gated_runs():
    """Verified=True is emitted at the FINAL stage (all gates passed), and failures
    are recorded so procedures can be retired."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "studio" / "supervisor.py").read_text(
        encoding="utf-8", errors="replace")
    assert "_learn_from_run(studio, verified=True)" in src
    assert "_learn_from_run(studio, verified=False" in src


def test_learning_never_breaks_a_run(monkeypatch):
    """Memory is best-effort — an exception inside it must not fail the build."""
    from engine.studio import supervisor

    def _boom(*a, **k):
        raise RuntimeError("memory exploded")

    monkeypatch.setattr(wm, "record_run", _boom)
    supervisor._learn_from_run({"goal": "x", "completed_stages": ["a"]}, verified=True)
