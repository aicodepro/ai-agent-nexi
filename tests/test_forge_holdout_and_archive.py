"""Ideas #82 (held-out eval) + #83 (archive/rollback) — assume Forge games its gate.

Forge asks ONE model call for `{name, function_code, test_code}`: the generator writes
the implementation AND the test that judges it. `def test_x(): assert True` therefore
"passes". The DGM paper measured 73.8% of self-improving code experiments gaming their
proxy exactly this way, which is why #82 insists the gate must not be the only judge.

These pin the defences:
  * a self-written test that CANNOT FAIL is rejected before install;
  * a tool that fails spec-derived held-out cases is rejected;
  * "could not verify independently" is never reported as a pass;
  * every installed version is archived OUTSIDE Forge's own directory and revertible.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.forge import archive, holdout_eval

GOOD = "def add(a, b):\n    return a + b\n"


# ---- #82: the self-written test must be capable of failing ----------------------

@pytest.mark.parametrize("test_src,expect", [
    ("def test_add():\n    add(1, 2)\n    assert True\n", "vacuous"),
    ("def test_add():\n    assert 1 + 1 == 2\n", "never calls"),
    ("def test_add():\n    add(1, 2)\n", "no assertion"),
    ("", "no test"),
    ("def test_add(:\n", "does not parse"),
])
def test_inadequate_tests_are_rejected(test_src, expect):
    verdict = holdout_eval.test_adequacy(GOOD, test_src, "add")
    assert verdict["ok"] is False
    assert expect in verdict["reason"], verdict


def test_a_real_test_is_accepted():
    verdict = holdout_eval.test_adequacy(GOOD, "def test_add():\n    assert add(1, 2) == 3\n", "add")
    assert verdict["ok"] is True
    assert verdict["calls_function"] is True


# ---- #82: held-out cases derived from the SPEC, not the implementation ----------

def test_holdout_cases_render_as_runnable_asserts():
    src = holdout_eval.cases_to_test("add", [
        {"args": [1, 2], "kwargs": {}, "expected": 3},
        {"args": [-1, 1], "kwargs": {}, "expected": 0},
    ])
    assert "from tool_under_test import add" in src
    assert "assert add(1, 2) == 3" in src
    assert "assert add(-1, 1) == 0" in src


def test_a_wrong_tool_fails_the_holdout_even_if_its_own_test_passed():
    """The whole point: its own test passes, the independent check catches it."""
    cases = [{"args": [1, 2], "kwargs": {}, "expected": 3}]
    verdict = holdout_eval.evaluate(
        "add two numbers", "def add(a,b): return a-b\n",
        "def test_add():\n    assert add(2, 2) == 0\n",   # true for subtraction!
        "add",
        generate_fn=lambda *_a, **_k: {"cases": cases},
        run_test=lambda f, t, timeout=10.0: {"passed": False, "output": "expected 3 got -1"},
    )
    assert verdict["ok"] is False
    assert "held-out" in verdict["reason"]


def test_unverifiable_degrades_to_partial_and_says_so(monkeypatch):
    """Offline / no model: static adequacy still ran, so this is PARTIAL verification.
    It must never be *reported* as full verification, and must be visibly flagged."""
    monkeypatch.delenv("NEXI_FORGE_REQUIRE_HOLDOUT", raising=False)
    verdict = holdout_eval.evaluate(
        "add two numbers", GOOD, "def test_add():\n    assert add(1, 2) == 3\n", "add",
        generate_fn=lambda *_a, **_k: {"cases": []},
    )
    assert verdict["partial"] is True
    assert "PARTIAL" in verdict["reason"]
    assert verdict["holdout_passed"] is None, "must not claim a held-out pass it never ran"


def test_strict_mode_refuses_partial_verification(monkeypatch):
    """A deployment can demand real independent verification."""
    monkeypatch.setenv("NEXI_FORGE_REQUIRE_HOLDOUT", "1")
    verdict = holdout_eval.evaluate(
        "add two numbers", GOOD, "def test_add():\n    assert add(1, 2) == 3\n", "add",
        generate_fn=lambda *_a, **_k: {"cases": []},
    )
    assert verdict["ok"] is False
    assert "REQUIRE_HOLDOUT" in verdict["reason"]


def test_a_vacuous_test_is_rejected_even_in_partial_mode(monkeypatch):
    """Degrading to partial must NOT reopen the hole it exists to close."""
    monkeypatch.delenv("NEXI_FORGE_REQUIRE_HOLDOUT", raising=False)
    verdict = holdout_eval.evaluate(
        "add two numbers", GOOD, "def test_add():\n    add(1, 2)\n    assert True\n", "add",
        generate_fn=lambda *_a, **_k: {"cases": []},
    )
    assert verdict["ok"] is False, "a vacuous test must fail regardless of held-out availability"


def test_a_correct_tool_passes_both_judges():
    verdict = holdout_eval.evaluate(
        "add two numbers", GOOD, "def test_add():\n    assert add(1, 2) == 3\n", "add",
        generate_fn=lambda *_a, **_k: {"cases": [{"args": [1, 2], "kwargs": {}, "expected": 3}]},
        run_test=lambda f, t, timeout=10.0: {"passed": True, "output": ""},
    )
    assert verdict["ok"] is True
    assert verdict["holdout_passed"] is True


# ---- #83: archive + rollback ----------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXI_FORGE_ARCHIVE", str(tmp_path / "arch"))
    yield


def test_archive_is_outside_forge_writable_dir(monkeypatch, tmp_path):
    """A forged tool must not be able to delete the record of what it replaced (#84)."""
    monkeypatch.delenv("NEXI_FORGE_ARCHIVE", raising=False)
    root = str(archive.archive_root()).replace("\\", "/")
    assert "custom_tools" not in root, "archive lives where Forge installs — it could erase its own history"


def test_every_version_is_kept():
    archive.record("adder", "v1", spec="add")
    archive.record("adder", "v2", spec="changed")
    archive.record("adder", "v3", spec="changed again")
    assert archive.versions("adder") == 3
    assert archive.get_source("adder", 1) == "v1"
    assert archive.get_source("adder") == "v3"       # latest by default


def test_rollback_restores_the_previous_version():
    archive.record("adder", "def add(a,b): return a+b", spec="working")
    archive.record("adder", "def add(a,b): return a-b", spec="BROKEN")
    installed = {}
    res = archive.rollback("adder", install_fn=lambda n, s, m: installed.setdefault(n, s) or "p")
    assert res["ok"] and res["restored_version"] == 1
    assert "a+b" in installed["adder"]


def test_rollback_can_target_a_specific_version():
    for i in range(1, 4):
        archive.record("t", f"version{i}")
    installed = {}
    res = archive.rollback("t", to_version=1, install_fn=lambda n, s, m: installed.setdefault(n, s) or "p")
    assert res["ok"] and installed["t"] == "version1"


def test_rollback_is_itself_archived_so_history_stays_append_only():
    archive.record("t", "a")
    archive.record("t", "b")
    archive.rollback("t", install_fn=lambda n, s, m: "p")
    assert archive.versions("t") == 3, "rollback must be recorded, not overwrite history"


def test_rollback_with_no_history_is_refused_not_crashed():
    res = archive.rollback("never-existed", install_fn=lambda n, s, m: "p")
    assert res["ok"] is False
    assert "no earlier version" in res["message"]


def test_history_reports_why_a_version_was_accepted():
    archive.record("t", "src", verdict={"ok": True, "reason": "passed 3 held-out case(s)"},
                   scan={"safe": True}, spec="s")
    entry = archive.history("t")[0]
    assert entry["verdict"]["reason"].startswith("passed 3")
    assert entry["scan_safe"] is True


# ---- pipeline wiring -------------------------------------------------------------

def test_forge_engine_verifies_before_installing():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "forge" / "forge_engine.py").read_text(
        encoding="utf-8", errors="replace")
    assert "holdout_eval.evaluate(" in src
    assert "archive.record(" in src
    # verification must come BEFORE the install call
    assert src.index("holdout_eval.evaluate(") < src.index("tool_installer.install(name, fcode")
