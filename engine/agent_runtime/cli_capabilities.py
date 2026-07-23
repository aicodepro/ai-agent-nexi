"""What can each agent CLI actually do, right now?

NEXI drives three CLIs (claude-code, opencode, hermes) but until now had no way to KNOW
what each one contains — so it could not answer "which CLI should run this task?" without
someone hardcoding the answer. Darsh's rule is no hardcoding, so this DISCOVERS:

  * is the CLI installed (and where)
  * which skills it has (scans its real skill home for <name>/SKILL.md)
  * which agents/roles it exposes
  * which model pool it draws from (delegated to model_policy — free-first, self-healing)

Everything is read from the filesystem/PATH at call time. Add a CLI, install a skill, or
delete one, and this reflects it on the next scan — nothing to edit here.

Routing rule NEXI uses: pick the CLI that ACTUALLY has the skill the task needs; break
ties by the role fit for the task kind. Never assume a capability that wasn't observed —
same anti-hallucination principle as mcp_preflight (probe, don't trust config).
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

# Where each CLI keeps its skills. Env override first (a machine may relocate them),
# then the documented default. These are LOCATIONS to scan, not capability claims.
_SKILL_HOMES: dict[str, list[str]] = {
    "hermes": ["${HERMES_HOME}/skills", "~/.hermes/skills"],
    "opencode": ["${OPENCODE_CONFIG}/skills", "~/.config/opencode/skills"],
    "claude-code": ["~/.claude/skills"],
}
_AGENT_HOMES: dict[str, list[str]] = {
    "hermes": ["${HERMES_HOME}/agents", "~/.hermes/agents"],
    "opencode": ["${OPENCODE_CONFIG}/agents", "~/.config/opencode/agents"],
    "claude-code": ["~/.claude/agents"],
}
_EXECUTABLES = {"hermes": "hermes", "opencode": "opencode", "claude-code": "claude"}

_CACHE: dict[str, dict] = {}
_CACHE_LOCK = threading.RLock()


def _ttl() -> float:
    try:
        return max(5.0, float(os.getenv("NEXI_CLI_CAPS_TTL_S", "300")))
    except ValueError:
        return 300.0


def _expand(candidates: list[str]) -> list[Path]:
    out = []
    for raw in candidates:
        s = raw
        for var in ("HERMES_HOME", "OPENCODE_CONFIG"):
            token = "${" + var + "}"
            if token in s:
                val = (os.getenv(var) or "").strip()
                if not val:
                    s = ""
                    break
                s = s.replace(token, val)
        if s:
            out.append(Path(os.path.expanduser(s)))
    return out


def _first_existing(candidates: list[str]) -> Path | None:
    for p in _expand(candidates):
        if p.exists():
            return p
    return None


def _scan_skills(home: Path | None) -> list[str]:
    """A skill is a directory containing SKILL.md. Hermes/OpenCode both use this shape —
    a FLAT foo.md is NOT loaded (that silently broke the oh-my-hermes install)."""
    if not home or not home.exists():
        return []
    out = []
    try:
        for child in home.iterdir():
            if child.is_dir() and not child.name.startswith(".") and (child / "SKILL.md").exists():
                out.append(child.name)
    except OSError:
        return []
    return sorted(out)


def _scan_agents(home: Path | None) -> list[str]:
    if not home or not home.exists():
        return []
    try:
        return sorted(p.stem for p in home.glob("*.md") if p.is_file())
    except OSError:
        return []


def discover_cli(name: str, *, force: bool = False) -> dict:
    """Observed capabilities of one CLI. Cached for TTL; nothing is assumed."""
    with _CACHE_LOCK:
        cached = _CACHE.get(name)
        if cached and not force and (time.time() - cached["_at"]) < _ttl():
            return cached
        exe = _EXECUTABLES.get(name, name)
        path = shutil.which(exe)
        skill_home = _first_existing(_SKILL_HOMES.get(name, []))
        agent_home = _first_existing(_AGENT_HOMES.get(name, []))
        skills = _scan_skills(skill_home)
        agents = _scan_agents(agent_home)
        info = {
            "_at": time.time(),
            "name": name,
            "installed": bool(path),
            "path": path or "",
            "skill_home": str(skill_home) if skill_home else "",
            "agent_home": str(agent_home) if agent_home else "",
            "skills": skills,
            "skill_count": len(skills),
            "agents": agents,
            "agent_count": len(agents),
        }
        _CACHE[name] = info
        return info


def all_clis(*, force: bool = False) -> dict[str, dict]:
    return {n: discover_cli(n, force=force) for n in _EXECUTABLES}


def clis_with_skill(skill: str) -> list[str]:
    """Which installed CLIs actually have this skill — observed, not assumed."""
    want = (skill or "").strip().lower()
    if not want:
        return []
    return [n for n, info in all_clis().items()
            if info["installed"] and any(s.lower() == want for s in info["skills"])]


def parity_report() -> dict:
    """Which skills are missing from which CLI. Darsh's rule: everything in OpenCode
    must also be in Hermes. This makes a parity break visible instead of silent."""
    caps = all_clis()
    present = {n: {s.lower() for s in c["skills"]} for n, c in caps.items() if c["installed"]}
    union = set().union(*present.values()) if present else set()
    return {
        "total_unique_skills": len(union),
        "per_cli": {n: len(s) for n, s in present.items()},
        "missing": {n: sorted(union - s) for n, s in present.items()},
        "in_sync": all(len(union - s) == 0 for s in present.values()) if present else True,
    }


# How heavy is this work? This decides the MODEL TIER, not the CLI. Darsh's rule:
# strong models (Opus 4.8 / GPT-5.x) for real programming and planning; cheap free
# models (DeepSeek v4 Flash, MiniMax) for small/lightweight turns — to save tokens,
# money and time without making small edits wait on an expensive model.
HEAVY_TASKS = frozenset({"orchestration", "architecture", "code", "self_improve",
                         "research", "debug", "review", "security"})
LIGHT_TASKS = frozenset({"quick", "chat", "format", "rename", "lookup", "summarize",
                         "test", "ui", "docs"})


def task_weight(task_kind: str) -> str:
    if task_kind in HEAVY_TASKS:
        return "heavy"
    if task_kind in LIGHT_TASKS:
        return "light"
    return "heavy"      # unknown work: don't cheap out on something that might matter


# ---- MODE selection -------------------------------------------------------------
# Model tier answers "how smart"; MODE answers "may it write?". Planning, research and
# audits must NOT edit the repo — running them write-enabled is how an agent "helpfully"
# refactors while it was only asked to look. Implementation obviously needs writes.
# Each CLI spells the modes differently, so NEXI picks the INTENT and we translate.
READ_ONLY_TASKS = frozenset({
    "orchestration", "architecture", "research", "review", "security",
    "plan", "analysis", "audit", "lookup", "chat",
})
WRITE_TASKS = frozenset({
    "code", "implementation", "test", "docs", "ui", "self_improve", "debug", "quick",
})

def _unattended() -> bool:
    """Operator opt-in for prompt-free writes (env only, never model-settable)."""
    return str(os.getenv("NEXI_STUDIO_UNATTENDED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _mode_names() -> dict[str, dict[str, str]]:
    """intent -> that CLI's actual flag value, resolved at call time.

    'auto' means acceptEdits by default: file edits are auto-approved but Bash still
    prompts, so an unattended run stalls waiting for a click. With NEXI_STUDIO_UNATTENDED=1
    'auto' becomes a genuinely prompt-free mode so the build finishes on its own.
    """
    claude_auto = "bypassPermissions" if _unattended() else "acceptEdits"
    return {
        "claude-code": {"plan": "plan", "auto": claude_auto},
        "opencode": {"plan": "plan", "auto": "build"},   # opencode grants tools via config
        "hermes": {"plan": "plan", "auto": "auto"},
    }


def select_mode(task_kind: str) -> str:
    """'plan' (read-only) or 'auto' (may write), from the KIND of work."""
    if task_kind in READ_ONLY_TASKS:
        return "plan"
    if task_kind in WRITE_TASKS:
        return "auto"
    return "plan"       # unknown work: look before you touch


def mode_for(cli: str, task_kind: str) -> str:
    """The mode string this specific CLI expects."""
    names = _mode_names()
    intent = select_mode(task_kind)
    return names.get(cli, names["claude-code"]).get(intent, intent)


def active_cli() -> str:
    """THE ONE CLI in charge. Darsh picks it; every task runs there.

    NEXI does not spread a job across three CLIs — all three are kept at capability
    parity precisely so that whichever one is selected can do the whole pipeline
    (orchestrate -> plan -> research -> build -> test). Falls back to whatever is
    actually installed rather than insisting on an absent CLI.
    """
    chosen = (os.getenv("NEXI_AGENT_RUNTIME_PROVIDER") or "").strip().lower()
    alias = {"claude": "claude-code", "claude_code": "claude-code", "open-code": "opencode"}
    chosen = alias.get(chosen, chosen)
    caps = all_clis()
    if chosen and caps.get(chosen, {}).get("installed"):
        return chosen
    for name in ("opencode", "claude-code", "hermes"):
        if caps.get(name, {}).get("installed"):
            return name
    return ""


def route_task(task_kind: str, required_skill: str = "", cli: str = "") -> dict:
    """Resolve a task to (the ONE active CLI, a model chain sized to the work).

    The CLI does NOT change per task — only the model tier does. Heavy work gets the
    strong models; light work gets the cheap free ones. model_policy still orders the
    chain free-first and skips models the health tracker has benched.
    """
    target = (cli or active_cli()).strip()
    caps = all_clis()
    if not target:
        return {"cli": "", "models": [], "task_kind": task_kind, "weight": "",
                "warning": "No agent CLI is installed."}

    result = {"cli": target, "task_kind": task_kind, "weight": task_weight(task_kind),
              "mode": mode_for(target, task_kind),        # plan vs auto (may it write?)
              "mode_intent": select_mode(task_kind),
              "required_skill": required_skill}

    # A missing skill is reported, never silently routed elsewhere — the whole point of
    # capability parity is that the selected CLI should already have it.
    if required_skill and not any(s.lower() == required_skill.lower()
                                  for s in caps.get(target, {}).get("skills", [])):
        others = [c for c in clis_with_skill(required_skill) if c != target]
        result["warning"] = (f"'{target}' does not have skill '{required_skill}'."
                             + (f" Available on: {', '.join(others)}." if others else
                                " No installed CLI has it."))

    try:
        from engine.agent_runtime.model_policy import model_chain
        result["models"] = model_chain(target, task_kind)
    except Exception:
        result["models"] = []
    return result


def summary() -> str:
    """One-liner NEXI can say out loud."""
    caps = all_clis()
    parts = [f"{n} ({c['skill_count']} skills, {c['agent_count']} agents)"
             for n, c in caps.items() if c["installed"]]
    missing = [n for n, c in caps.items() if not c["installed"]]
    text = "Connected CLIs: " + (", ".join(parts) if parts else "none")
    if missing:
        text += f". Not installed: {', '.join(missing)}."
    return text


def _demo() -> None:
    caps = all_clis(force=True)
    assert set(caps) == {"hermes", "opencode", "claude-code"}
    for name, c in caps.items():
        assert isinstance(c["skills"], list) and c["skill_count"] == len(c["skills"])
    r = route_task("code")
    assert "cli" in r and "models" in r
    print("cli_capabilities._demo OK ->", summary())


if __name__ == "__main__":
    import json
    import sys
    if "--demo" in sys.argv:
        _demo()
    elif "--parity" in sys.argv:
        print(json.dumps({k: v for k, v in parity_report().items() if k != "missing"}, indent=2))
    else:
        print(summary())
        for kind in ("orchestration", "code", "test", "research"):
            r = route_task(kind)
            print(f"  {kind:14s} -> {r['cli'] or '(none)':12s} models={r['models'][:2]}")
