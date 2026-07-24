"""Unattended writes: opt-in, never the default, never model-settable.

Darsh's need: in `acceptEdits` the agent still stops and waits for a "yes" on Bash,
so an autonomous Studio build stalls on the first command. Truly prompt-free operation
requires Claude Code's `bypassPermissions`, which governance previously rejected
outright as unsafe.

The resolution is a gate, not a removal:
  * DEFAULT stays acceptEdits — nothing changes for anyone who does not opt in;
  * NEXI_STUDIO_UNATTENDED=1 (env only, so a model can never set it) switches WRITING
    stages to a prompt-free mode;
  * read-only stages stay 'plan' either way — unattended must not mean "may now edit
    during a security audit".
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.agent_runtime import cli_capabilities as cc
from engine.studio import governance as g

_FLAG = "NEXI_STUDIO_UNATTENDED"


@pytest.fixture
def attended(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)


@pytest.fixture
def unattended(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")


# ---- default is unchanged and safe ----------------------------------------------

def test_default_write_mode_is_accept_edits(attended):
    assert g.permission_mode_for("implementation") == "acceptEdits"
    assert cc.mode_for("claude-code", "code") == "acceptEdits"


def test_default_rejects_bypass_permissions(attended):
    """Without the opt-in, bypassPermissions must still be refused."""
    with pytest.raises(g.GovernanceError) as exc:
        g.load_trusted_agents(["project-strategist"], {}, authoritative_permission_mode="bypassPermissions")
    assert "NEXI_STUDIO_UNATTENDED" in str(exc.value)


# ---- opt-in enables prompt-free writes -------------------------------------------

def test_opt_in_makes_writing_stages_prompt_free(unattended):
    assert g.permission_mode_for("implementation") == "bypassPermissions"
    assert cc.mode_for("claude-code", "code") == "bypassPermissions"


def test_opt_in_does_not_loosen_read_only_stages(unattended):
    """The whole safety story: unattended != 'may edit during an audit'."""
    for stage in ("requirements", "research", "architecture", "sprint_plan",
                  "security_review", "integration", "release"):
        assert g.permission_mode_for(stage) == "plan", f"{stage} became writable"
    for kind in ("architecture", "research", "security", "review"):
        assert cc.select_mode(kind) == "plan"


def test_mode_is_evaluated_per_call_not_frozen_at_import(monkeypatch):
    """REGRESSION: the mode map was built at import time, so setting the flag later
    (or in a test) was silently ignored."""
    monkeypatch.delenv(_FLAG, raising=False)
    before = g.permission_mode_for("implementation")
    monkeypatch.setenv(_FLAG, "1")
    after = g.permission_mode_for("implementation")
    assert before != after, "permission mode is frozen at import — env changes ignored"


def test_canonical_mapping_reflects_the_flag(unattended):
    """The legacy CANONICAL_PERMISSION_MODES lookup must agree with the function."""
    assert g.CANONICAL_PERMISSION_MODES["implementation"] == "bypassPermissions"
    assert g.CANONICAL_PERMISSION_MODES["architecture"] == "plan"


# ---- the gate cannot be opened by a model ----------------------------------------

def test_flag_is_read_from_env_only(attended):
    """A model supplying permissionMode in agent data must not enable bypass."""
    with pytest.raises(g.GovernanceError):
        g.load_trusted_agents(["project-strategist"], {}, authoritative_permission_mode="bypassPermissions")


def test_unknown_mode_still_rejected(unattended):
    """Opting in widens ONE mode, it does not disable validation."""
    with pytest.raises(g.GovernanceError):
        g.load_trusted_agents(["project-strategist"], {}, authoritative_permission_mode="totallyMadeUp")


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "on", "ON"])
def test_flag_accepts_normal_truthy_spellings(monkeypatch, truthy):
    monkeypatch.setenv(_FLAG, truthy)
    assert g.permission_mode_for("implementation") == "bypassPermissions"


@pytest.mark.parametrize("falsy", ["0", "false", "no", "", "off"])
def test_flag_defaults_closed_for_anything_else(monkeypatch, falsy):
    monkeypatch.setenv(_FLAG, falsy)
    assert g.permission_mode_for("implementation") == "acceptEdits"
