"""NEXI switches MODE as well as model (Darsh: "auto mode to plan mode").

Model tier answers "how smart"; mode answers "may it write?". Running a planning,
research or security-audit stage write-enabled is how an agent asked only to LOOK ends
up refactoring the repo. Each CLI spells the modes differently (claude-code
plan/acceptEdits, opencode plan/build), so NEXI picks the INTENT and it is translated.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.agent_runtime import cli_capabilities as cc


@pytest.mark.parametrize("kind", ["orchestration", "architecture", "research",
                                  "review", "security", "analysis", "audit"])
def test_thinking_work_is_read_only(kind):
    assert cc.select_mode(kind) == "plan", f"{kind} must not be able to write"


@pytest.mark.parametrize("kind", ["code", "implementation", "test", "docs",
                                  "ui", "self_improve", "debug"])
def test_producing_work_may_write(kind):
    assert cc.select_mode(kind) == "auto", f"{kind} needs write access to do its job"


def test_unknown_work_defaults_to_read_only():
    """Look before you touch — an unrecognised task must not get write access."""
    assert cc.select_mode("something-nobody-defined") == "plan"


@pytest.mark.parametrize("cli,kind,expected", [
    ("claude-code", "architecture", "plan"),
    ("claude-code", "code", "acceptEdits"),
    ("opencode", "architecture", "plan"),
    ("opencode", "code", "build"),        # opencode calls write-mode "build"
    ("hermes", "code", "auto"),
])
def test_mode_is_translated_per_cli(cli, kind, expected):
    assert cc.mode_for(cli, kind) == expected


def test_route_task_reports_both_model_and_mode(monkeypatch, tmp_path):
    sk = tmp_path / "skills"
    (sk / "a").mkdir(parents=True)
    (sk / "a" / "SKILL.md").write_text("---\nname: a\n---\n", encoding="utf-8")
    monkeypatch.setitem(cc._SKILL_HOMES, "opencode", [str(sk)])
    monkeypatch.setattr(cc.shutil, "which", lambda e: f"/bin/{e}")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    cc._CACHE.clear()

    plan_task = cc.route_task("architecture")
    build_task = cc.route_task("code")
    assert plan_task["mode"] == "plan"
    assert build_task["mode"] == "build"
    assert plan_task["cli"] == build_task["cli"] == "opencode", "same CLI, different mode"


# ---- Studio wiring --------------------------------------------------------------

def test_studio_read_only_stages_never_get_write_mode():
    """Analysis/audit stages must be read-only; implementation must not be."""
    from engine.studio.supervisor import _STAGE_TASK_KIND
    for stage in ("requirements", "research", "architecture", "sprint_plan",
                  "security_review", "integration", "release"):
        assert cc.select_mode(_STAGE_TASK_KIND[stage]) == "plan", f"{stage} could write"
    for stage in ("implementation", "developer_tests", "qa", "closeout"):
        assert cc.select_mode(_STAGE_TASK_KIND[stage]) == "auto", f"{stage} cannot write"


def test_supervisor_sets_permission_mode_from_task_kind():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "studio" / "supervisor.py").read_text(
        encoding="utf-8", errors="replace")
    assert "mode_for(provider, task_kind)" in src
    assert 'kwargs["permission_mode"]' in src


# ---- four Claude tiers ----------------------------------------------------------

def test_all_four_claude_tiers_are_used():
    """haiku, sonnet, fable and opus must each earn a place — not just opus+haiku."""
    from engine.agent_runtime.model_policy import POOLS
    used = set(POOLS["claude-code"]["tasks"].values())
    for tier in ("claude-haiku-4-5", "claude-sonnet-5", "claude-fable-5", "claude-opus-4-8"):
        assert tier in used, f"{tier} is never selected for any task"


def test_hardest_work_gets_opus_and_trivial_gets_haiku():
    from engine.agent_runtime.model_policy import POOLS
    t = POOLS["claude-code"]["tasks"]
    assert t["architecture"] == "claude-opus-4-8"
    assert t["self_improve"] == "claude-opus-4-8", "self-modification must use the best model"
    assert t["quick"] == "claude-haiku-4-5"
    assert t["chat"] == "claude-haiku-4-5"
