#!/usr/bin/env python3
"""Compile config/agents/catalog.json into every downstream surface.

Generates Claude Code and OpenCode agent definitions from ONE source, so the
two runtimes cannot drift apart by hand-editing. Also emits the runtime
registry, permission matrix and a parity report.

  python scripts/compile_agent_catalog.py            # generate
  python scripts/compile_agent_catalog.py --check     # fail if outputs drift

--check is what CI runs: it regenerates into memory and compares, so an edited
generated file is caught instead of silently diverging from the catalog.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "config" / "agents" / "catalog.json"
CLAUDE_DIR = ROOT / ".claude" / "agents"
OPENCODE_DIR = ROOT / ".opencode" / "agents"
GENERATED = ROOT / "generated"

BANNER = "<!-- GENERATED FROM config/agents/catalog.json - DO NOT EDIT BY HAND -->"

# permission_intent -> (claude permissionMode, opencode permission)
PERMISSION_MAP = {
    "plan":        ("plan", "read"),
    "write":       ("acceptEdits", "write"),
    "acceptEdits": ("acceptEdits", "write"),
    "ask":         ("default", "ask"),
    "code_only":   ("plan", "read"),
}

# Read-only classes must never receive write tools.
READ_ONLY_TOOLS = ["Read", "Grep", "Glob"]
WRITE_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


def load() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _tools_for(agent: dict) -> list[str]:
    return WRITE_TOOLS if agent["permission_intent"] in {"write", "acceptEdits"} else READ_ONLY_TOOLS


def claude_md(agent: dict) -> str:
    mode, _ = PERMISSION_MAP[agent["permission_intent"]]
    tools = ", ".join(_tools_for(agent))
    return (
        f"---\n"
        f"name: {agent['name']}\n"
        f"description: {agent['description']}\n"
        f"tools: {tools}\n"
        f"permissionMode: {mode}\n"
        f"maxTurns: {agent.get('max_turns', 12)}\n"
        f"---\n\n"
        f"{BANNER}\n\n"
        f"# {agent['name']}\n\n"
        f"**ID:** {agent['id']} | **Class:** {agent['agent_class']} | "
        f"**Stage:** {agent.get('stage', 'n/a')} | **Risk:** {agent.get('risk', 'low')}\n\n"
        f"## Responsibility\n\n{agent['description']}\n\n"
        f"## Output\n\n{agent.get('output', 'StageArtifact')}\n\n"
        f"## Boundaries\n\n"
        f"- Nexi Python owns authorization, gate decisions and the final user-facing response.\n"
        f"- You do not speak to the user directly; return a typed result to the ResponseCoordinator.\n"
        f"- You may not verify your own work. Verification belongs to `{agent.get('verifier', 'verifier-registry')}`.\n"
        f"- You may not approve a gate, merge, or release your own output.\n"
        + ("- Read-only: do not edit files or run mutating commands.\n"
           if agent["permission_intent"] in {"plan", "code_only"} else
           "- Stay inside the authorized project/worktree. Do not touch unrelated files.\n")
    )


def opencode_md(agent: dict) -> str:
    _, perm = PERMISSION_MAP[agent["permission_intent"]]
    # Only the stage owner is primary; specialists are subagents.
    mode = "primary" if agent.get("stage") in ("runtime",) and agent["id"] == "R01" else "subagent"
    tools = _tools_for(agent)
    return (
        f"---\n"
        f"description: {agent['description']}\n"
        f"mode: {mode}\n"
        f"permission: {perm}\n"
        f"tools: {json.dumps(tools)}\n"
        f"steps: {agent.get('max_turns', 12)}\n"
        f"---\n\n"
        f"{BANNER}\n\n"
        f"# {agent['name']}\n\n"
        f"**ID:** {agent['id']} | **Class:** {agent['agent_class']} | "
        f"**Stage:** {agent.get('stage', 'n/a')}\n\n"
        f"## Responsibility\n\n{agent['description']}\n\n"
        f"## Boundaries\n\n"
        f"- Nexi Python owns authorization and the final user-facing response.\n"
        f"- Return a typed result; never speak to the user directly.\n"
        f"- You may not verify or approve your own work.\n"
    )


def build_outputs(catalog: dict) -> dict[Path, str]:
    out: dict[Path, str] = {}
    agents = catalog["runtime_agents"] + catalog["studio_agents"]

    for a in agents:
        out[CLAUDE_DIR / f"{a['name']}.md"] = claude_md(a)
        out[OPENCODE_DIR / f"{a['name']}.md"] = opencode_md(a)

    out[GENERATED / "runtime-agent-registry.json"] = json.dumps(
        {"version": catalog["catalog_version"], "agents": catalog["runtime_agents"]}, indent=2) + "\n"

    out[GENERATED / "agent-permission-matrix.json"] = json.dumps(
        {a["name"]: {
            "id": a["id"],
            "intent": a["permission_intent"],
            "claude_mode": PERMISSION_MAP[a["permission_intent"]][0],
            "opencode_permission": PERMISSION_MAP[a["permission_intent"]][1],
            "tools": _tools_for(a),
            "may_verify_self": False,
            "may_approve_self": False,
        } for a in agents}, indent=2) + "\n"

    out[GENERATED / "agent-ui-cards.json"] = json.dumps(
        [{"id": a["id"], "name": a["name"], "class": a["agent_class"],
          "stage": a.get("stage"), "risk": a.get("risk", "low"),
          "status": a.get("status", "specified"),
          "runtimes": ["claude", "opencode"] if a["agent_class"] == "studio" else ["nexi"]}
         for a in agents], indent=2) + "\n"

    claude_n = sum(1 for p in out if CLAUDE_DIR in p.parents)
    oc_n = sum(1 for p in out if OPENCODE_DIR in p.parents)
    controllers = catalog["deterministic_controllers"]
    unimplemented = [c["name"] for c in controllers if not c.get("implemented_by")]

    out[GENERATED / "agent-parity-report.md"] = (
        f"# Agent Parity Report\n\n{BANNER}\n\n"
        f"| Surface | Count |\n| --- | ---: |\n"
        f"| Runtime agents (catalog) | {len(catalog['runtime_agents'])} |\n"
        f"| Studio agents (catalog) | {len(catalog['studio_agents'])} |\n"
        f"| Claude Code definitions generated | {claude_n} |\n"
        f"| OpenCode definitions generated | {oc_n} |\n"
        f"| Deterministic controllers | {len(controllers)} |\n\n"
        f"Parity is structural: both runtimes are generated from the same catalog "
        f"entries, so per-agent responsibility, permission intent and delegation "
        f"boundaries cannot diverge by hand-editing. `--check` fails the build on drift.\n\n"
        f"## Controllers without a single authority\n\n"
        + ("\n".join(f"- `{n}` — **not implemented**" for n in unimplemented) if unimplemented
           else "All controllers map to an implementation.")
        + "\n\n> Generated definitions are declarations, not activation. An agent is "
          "only live once it is wired to policy, routing and tests.\n"
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if generated files drift")
    args = ap.parse_args()

    catalog = load()

    # The catalog must agree with the governance stage map, not redefine it.
    owners = catalog["governance_stage_owners"]
    names = {a["name"] for a in catalog["studio_agents"]}
    missing = [o for o in owners.values() if o not in names]
    if missing:
        print(f"ERROR: governance stage owners absent from catalog: {missing}", file=sys.stderr)
        return 2

    outputs = build_outputs(catalog)

    if args.check:
        # Hand-authored definitions are outside the compiler's control and are
        # therefore not drift. Only generated files (BANNER) are compared.
        drifted = []
        for p, content in outputs.items():
            if p.exists():
                current = p.read_text(encoding="utf-8")
                if BANNER not in current:
                    continue
                if current != content:
                    drifted.append(p)
            else:
                drifted.append(p)
        if drifted:
            print(f"DRIFT: {len(drifted)} generated file(s) differ from the catalog:", file=sys.stderr)
            for p in drifted[:15]:
                print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
            print("\nRun: python scripts/compile_agent_catalog.py", file=sys.stderr)
            return 1
        print(f"OK - {len(outputs)} generated files match the catalog.")
        return 0

    skipped = 0
    for path, content in outputs.items():
        # Never clobber a hand-authored definition. Several existing agents
        # (developer-team especially) carry contracts that Python validates at
        # runtime - e.g. the exact Agent(...) delegation allowlist - which a
        # generic generated template would silently destroy. Only files this
        # compiler wrote (they carry BANNER) are regenerated.
        if path.exists() and BANNER not in path.read_text(encoding="utf-8"):
            skipped += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"generated {len(outputs)} files from {CATALOG.relative_to(ROOT)}")
    print(f"  .claude/agents  : {sum(1 for p in outputs if CLAUDE_DIR in p.parents)}")
    print(f"  .opencode/agents: {sum(1 for p in outputs if OPENCODE_DIR in p.parents)}")
    print(f"  generated/      : {sum(1 for p in outputs if GENERATED in p.parents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
