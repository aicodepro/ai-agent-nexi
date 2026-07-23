"""Forge orchestrator: spec -> generate -> scan -> sandbox test -> gate -> install.

Retries with the test error fed back to the generator. Phase 1 installs SAFE
tools automatically; RISKY tools stop at needs_approval (Phase 2 wires the gate).
"""
from engine.forge import (accept_gate, archive, code_generator, holdout_eval,
                          safety_scan, sandbox_runner, tool_installer)


def forge_tool(spec: str, *, generate_fn=None, max_retries: int = 2, timeout: float = 10.0) -> dict:
    """Forge a tool for `spec`. Returns a result dict with `ok`, `status`, `message`."""
    if not str(spec or "").strip():
        return {"ok": False, "status": "failed", "message": "empty spec"}

    last_error = ""
    error = None
    for attempt in range(max_retries + 1):
        gen_spec = spec if attempt == 0 else (
            f"{spec}\n\nThe previous attempt failed its test:\n{last_error}\nFix the code so the test passes."
        )
        try:
            gen = code_generator.generate(gen_spec, generate_fn=generate_fn)
        except Exception as exc:
            last_error = f"generation/parse error: {type(exc).__name__}: {exc}"
            error = {"stage": "generation", "type": type(exc).__name__, "message": str(exc)}
            continue

        name, fcode, tcode = gen["name"], gen["function_code"], gen["test_code"]
        if not (name and fcode and tcode):
            last_error = "generator returned empty name/function/test"
            continue

        # Gate BEFORE executing. The sandbox is process isolation + timeout, not a
        # container (see sandbox_runner) — so code the static scan already flagged as
        # touching fs/network/subprocess/exec must never be run at all, not run first
        # and blocked from install afterwards.
        scan = safety_scan.scan(fcode)
        if accept_gate.decide(scan) == "approve":
            return {
                "ok": False, "status": "needs_approval", "name": name, "scan": scan,
                "message": (f"Tool '{name}' touches the system ({scan['reason']}) — it needs "
                            f"your approval before I build it. I have not run it."),
            }

        try:
            test = sandbox_runner.run_test(fcode, tcode, timeout=timeout)
        except Exception as exc:
            last_error = f"sandbox error: {type(exc).__name__}: {exc}"
            error = {"stage": "sandbox", "type": type(exc).__name__, "message": str(exc)}
            continue
        if not test["passed"]:
            last_error = test["output"]
            continue

        # The generator wrote BOTH the function and the test that judges it, so the test
        # passing proves very little on its own — `assert True` passes. Idea #82: check
        # it with judges the generator never saw (static adequacy + held-out cases
        # derived from the spec alone). A tool that cannot be independently verified is
        # NOT auto-installed; it goes to approval, because "unverified" must never be
        # reported as "passed".
        try:
            verdict = holdout_eval.evaluate(spec, fcode, tcode, name,
                                            generate_fn=generate_fn, timeout=timeout)
        except Exception as exc:
            last_error = f"verification error: {type(exc).__name__}: {exc}"
            error = {"stage": "verification", "type": type(exc).__name__, "message": str(exc)}
            continue
        if not verdict["ok"]:
            return {
                "ok": False, "status": "needs_approval", "name": name, "scan": scan,
                "verdict": verdict,
                "message": (f"Tool '{name}' passed its own test but failed independent "
                            f"verification: {verdict['reason']}. Not installed — approve it "
                            f"explicitly if you still want it."),
            }

        try:
            path = tool_installer.install(name, fcode, {"spec": spec, "scan": scan,
                                                        "attempts": attempt + 1, "verdict": verdict})
        except Exception as exc:
            return {
                "ok": False, "status": "failed", "name": name,
                "error": {"stage": "install", "type": type(exc).__name__, "message": str(exc)},
                "message": f"Tool '{name}' passed verification but could not be installed: {exc}",
            }
        # Idea #83: archive every version so any self-modification can be reverted.
        archived = True
        archive_error = None
        try:
            archive.record(name, fcode, verdict=verdict, scan=scan, spec=spec)
        except Exception as exc:
            archived = False
            archive_error = {"type": type(exc).__name__, "message": str(exc)}
            print(f"[FORGE] archive_failed reason={type(exc).__name__}", flush=True)
        return {
            "ok": True, "status": "installed", "name": name, "path": path, "scan": scan,
            "verdict": verdict, "archived": archived, "archive_error": archive_error,
            "message": (f"Forged and installed '{name}' — {verdict['reason']}, "
                        f"classified safe. " + ("Archived for rollback." if archived else
                                                 "Warning: installed but not archived for rollback.")),
        }

    result = {
        "ok": False, "status": "failed",
        "message": f"Could not forge a working tool after {max_retries + 1} attempts. Last error: {last_error[:500]}",
    }
    if error:
        result["error"] = error
    return result


# ── Voice/agency-facing wrappers (Phase 2 wires these into the tool registry) ──
def nexi_forge_tool(spec: str = "", **_) -> dict:
    return forge_tool(spec)


def nexi_list_forged_tools(**_) -> dict:
    tools = tool_installer.list_forged()
    return {"ok": True, "tools": tools, "message": f"{len(tools)} forged tool(s): {', '.join(tools) or 'none'}"}


def nexi_remove_tool(name: str = "", **_) -> dict:
    ok = tool_installer.remove(name)
    return {"ok": ok, "message": f"Removed '{name}'." if ok else f"No forged tool named '{name}'."}


def nexi_rollback_tool(name: str = "", version: str = "", **_) -> dict:
    """Idea #83: one command to undo a self-modification that turned out worse."""
    if not str(name or "").strip():
        return {"ok": False, "message": "Tell me which forged tool to roll back."}
    target = None
    if str(version or "").strip():
        try:
            target = int(str(version).strip().lstrip("vV"))
        except ValueError:
            return {"ok": False, "message": f"'{version}' is not a version number."}
    return archive.rollback(str(name).strip(), to_version=target)


def nexi_tool_history(name: str = "", **_) -> dict:
    """What versions exist, and why each was accepted — a rollback should explain the
    mistake, not just undo it."""
    if not str(name or "").strip():
        return {"ok": False, "message": "Tell me which forged tool's history you want."}
    entries = archive.history(str(name).strip())
    if not entries:
        return {"ok": True, "versions": [], "message": f"No archived history for '{name}'."}
    summary = "; ".join(
        f"v{e['version']}{' (' + (e.get('verdict') or {}).get('reason', '')[:40] + ')' if e.get('verdict') else ''}"
        for e in entries[-5:])
    return {"ok": True, "versions": entries,
            "message": f"'{name}' has {len(entries)} archived version(s): {summary}"}
