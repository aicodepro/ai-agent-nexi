"""Canonical agent catalog: integrity, parity and non-clobbering.

The catalog is the single source for Claude Code and OpenCode agent
definitions. These tests protect three properties:
  1. the catalog agrees with the governance stage map (does not redefine it);
  2. generated files stay in sync with the catalog (drift fails CI);
  3. hand-authored definitions are never overwritten by generation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "config" / "agents" / "catalog.json"
COMPILER = ROOT / "scripts" / "compile_agent_catalog.py"
BANNER = "GENERATED FROM config/agents/catalog.json"


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_catalog_has_full_roster():
    c = _catalog()
    assert len(c["runtime_agents"]) == 15
    assert len(c["studio_agents"]) == 39
    assert len(c["deterministic_controllers"]) == 9


def test_catalog_agrees_with_governance_stage_owners():
    """The catalog must not contradict engine/studio/governance.py."""
    from engine.studio.governance import CANONICAL_STAGE_AGENTS

    c = _catalog()
    assert c["governance_stage_owners"] == CANONICAL_STAGE_AGENTS
    names = {a["name"] for a in c["studio_agents"]}
    for owner in CANONICAL_STAGE_AGENTS.values():
        assert owner in names, f"stage owner {owner} missing from catalog"


def test_every_agent_declares_required_fields():
    c = _catalog()
    required = {"id", "name", "version", "agent_class", "permission_intent",
                "description", "sha256"}
    for agent in c["runtime_agents"] + c["studio_agents"]:
        assert required <= set(agent), f"{agent.get('name')} missing {required - set(agent)}"


def test_read_only_agents_never_get_write_tools():
    """A plan-mode agent must not be handed Edit/Write/Bash."""
    matrix = json.loads((ROOT / "generated" / "agent-permission-matrix.json").read_text(encoding="utf-8"))
    for name, entry in matrix.items():
        if entry["intent"] in {"plan", "code_only"}:
            assert not ({"Edit", "Write", "Bash"} & set(entry["tools"])), \
                f"read-only agent {name} was granted write tools"


def test_no_agent_may_verify_or_approve_itself():
    matrix = json.loads((ROOT / "generated" / "agent-permission-matrix.json").read_text(encoding="utf-8"))
    for name, entry in matrix.items():
        assert entry["may_verify_self"] is False, name
        assert entry["may_approve_self"] is False, name


def test_both_runtimes_receive_the_same_agents():
    """Parity is structural: same names generated for Claude and OpenCode."""
    claude = {p.stem for p in (ROOT / ".claude" / "agents").glob("*.md")}
    opencode = {p.stem for p in (ROOT / ".opencode" / "agents").glob("*.md")}
    catalog_names = {a["name"] for a in _catalog()["runtime_agents"] + _catalog()["studio_agents"]}
    # Every catalog agent exists on both sides.
    assert catalog_names <= claude, f"missing from Claude: {sorted(catalog_names - claude)}"
    assert catalog_names <= opencode, f"missing from OpenCode: {sorted(catalog_names - opencode)}"


def test_generated_files_match_catalog():
    """Drift check - this is what CI runs."""
    result = subprocess.run(
        [sys.executable, str(COMPILER), "--check"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0, f"catalog drift:\n{result.stdout}\n{result.stderr}"


def test_hand_authored_definitions_are_not_generated():
    """Regression guard.

    Generation once overwrote 17 hand-authored agents, destroying contracts that
    Python validates at runtime (developer-team's Agent(...) delegation
    allowlist). Files without the generated banner must stay hand-owned.
    """
    dev_team = (ROOT / ".claude" / "agents" / "developer-team.md").read_text(encoding="utf-8")
    assert BANNER not in dev_team, "developer-team.md was clobbered by generation"
    assert "Agent(" in dev_team, "developer-team.md lost its delegation allowlist"


def test_controllers_are_code_not_personas():
    for c in _catalog()["deterministic_controllers"]:
        assert c["permission_intent"] == "code_only"
        assert "never become an LLM persona" in c["note"]
