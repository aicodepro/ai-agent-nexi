"""Probe or live-test a Nexi agent-runtime adapter in a disposable project."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.agent_runtime import registry, session
from engine.claude_code import verifier
from engine.memory_safety import redact_sensitive


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default=os.getenv("NEXI_AGENT_RUNTIME_PROVIDER") or "claude-code")
    parser.add_argument("--live", action="store_true", help="Run a real write-and-verify test in a disposable project.")
    parser.add_argument("--keep", action="store_true", help="Keep the disposable project after the live test.")
    return parser


def _live(provider: str, keep: bool) -> int:
    if not registry.runtime_enabled(provider):
        print(json.dumps({
            "ok": False,
            "provider_id": provider,
            "reason": "disabled",
            "help": "Set NEXI_AGENT_RUNTIME_ENABLED=1, or NEXI_CLAUDE_CODE_ENABLED=1 for Claude Code.",
        }, indent=2))
        return 2
    project = Path(tempfile.mkdtemp(prefix="nexi-agent-smoke-")).resolve()
    control = project.parent / f"{project.name}-control"
    control.mkdir(parents=True, exist_ok=True)
    (project / "README.md").write_text("# Nexi Agent Runtime Smoke Test\n", encoding="utf-8", newline="")
    baseline = verifier.workspace_snapshot(str(project))
    expected = f"NEXI_AGENT_RUNTIME_OK:{provider}"
    task = (
        "Create exactly one file named result.txt in the authorized target project. "
        f"Its complete UTF-8 content must be exactly: {expected}\n"
        "Do not modify README.md, do not create other files, do not use Git, and do not access external services."
    )
    agents_json = json.dumps({
        "smoke-developer": {
            "description": "Performs one bounded local smoke-test edit.",
            "prompt": "Follow the exact file contract. Make no unrelated changes.",
            "tools": ["Read", "Write"],
            "model": "inherit",
            "permissionMode": "acceptEdits",
            "maxTurns": 6,
        }
    })
    events: list[dict] = []
    result = session.run_task(
        task,
        project_dir=str(project),
        provider_id=provider,
        owner_id="nexi-agent-runtime-smoke",
        permission_mode="acceptEdits",
        agent_name="smoke-developer",
        agents_json=agents_json,
        control_cwd=str(control),
        baseline=baseline,
        run_tests_after=False,
        require_tests=False,
        on_event=lambda event: events.append(event),
    )
    output = project / "result.txt"
    actual = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
    final_snapshot = verifier.workspace_snapshot(str(project))
    change = verifier.compare_workspace(baseline, final_snapshot)
    exact_change = (
        not change.get("truncated")
        and change.get("added") == ["result.txt"]
        and change.get("modified") == []
        and change.get("deleted") == []
    )
    passed = bool(result.get("ok") and result.get("on_track") and actual == expected and exact_change)
    report = {
        "ok": passed,
        "provider_id": provider,
        "project": str(project),
        "agent_ok": bool(result.get("ok")),
        "nexi_verified_on_track": bool(result.get("on_track")),
        "expected_file_content_matched": actual == expected,
        "exact_workspace_change_matched": exact_change,
        "workspace_change": change,
        "session_id": str((result.get("dispatch") or {}).get("session_id") or ""),
        "event_count": len(events),
        "event_types": [str(event.get("type") or event.get("kind") or "unknown") for event in events[-10:] if isinstance(event, dict)],
        "event_preview": [redact_sensitive(json.dumps(event, default=str, ensure_ascii=True))[:600] for event in events[-8:]],
        "dispatch_reason": str((result.get("dispatch") or {}).get("reason") or ""),
        "dispatch_returncode": (result.get("dispatch") or {}).get("returncode"),
        "dispatch_is_error": bool((result.get("dispatch") or {}).get("is_error")),
        "dispatch_result_preview": redact_sensitive(str((result.get("dispatch") or {}).get("result") or ""))[:500],
        "message": result.get("message"),
    }
    print(json.dumps(report, indent=2))
    if keep:
        print(f"Kept smoke project: {project}")
    else:
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(control, ignore_errors=True)
    return 0 if passed else 1


def main() -> int:
    args = _parser().parse_args()
    try:
        provider = registry.canonical_provider_id(args.provider)
        status = registry.provider_status(provider)
    except ValueError as exc:
        print(json.dumps({"ok": False, "reason": "invalid_provider", "message": str(exc)}, indent=2))
        return 2
    print(json.dumps(status, indent=2))
    if not args.live:
        return 0 if status["available"] else 1
    if not status["available"]:
        return 1
    return _live(provider, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
