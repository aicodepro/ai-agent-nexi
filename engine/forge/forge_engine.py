"""Forge orchestrator: spec -> generate -> scan -> sandbox test -> gate -> install.

Retries with the test error fed back to the generator. Phase 1 installs SAFE
tools automatically; RISKY tools stop at needs_approval (Phase 2 wires the gate).
"""
from engine.forge import accept_gate, code_generator, safety_scan, sandbox_runner, tool_installer


def forge_tool(spec: str, *, generate_fn=None, max_retries: int = 2, timeout: float = 10.0) -> dict:
    """Forge a tool for `spec`. Returns a result dict with `ok`, `status`, `message`."""
    if not str(spec or "").strip():
        return {"ok": False, "status": "failed", "message": "empty spec"}

    last_error = ""
    for attempt in range(max_retries + 1):
        gen_spec = spec if attempt == 0 else (
            f"{spec}\n\nThe previous attempt failed its test:\n{last_error}\nFix the code so the test passes."
        )
        try:
            gen = code_generator.generate(gen_spec, generate_fn=generate_fn)
        except Exception as exc:
            last_error = f"generation/parse error: {type(exc).__name__}: {exc}"
            continue

        name, fcode, tcode = gen["name"], gen["function_code"], gen["test_code"]
        if not (name and fcode and tcode):
            last_error = "generator returned empty name/function/test"
            continue

        scan = safety_scan.scan(fcode)
        test = sandbox_runner.run_test(fcode, tcode, timeout=timeout)
        if not test["passed"]:
            last_error = test["output"]
            continue

        if accept_gate.decide(scan) == "approve":
            return {
                "ok": False, "status": "needs_approval", "name": name, "scan": scan,
                "message": (f"Tool '{name}' passed its test but touches the system "
                            f"({scan['reason']}) — it needs your approval before install (Phase 2)."),
            }

        path = tool_installer.install(name, fcode, {"spec": spec, "scan": scan, "attempts": attempt + 1})
        return {
            "ok": True, "status": "installed", "name": name, "path": path, "scan": scan,
            "message": f"Forged and installed '{name}' — test passed, classified safe.",
        }

    return {
        "ok": False, "status": "failed",
        "message": f"Could not forge a working tool after {max_retries + 1} attempts. Last error: {last_error[:500]}",
    }


# ── Voice/agency-facing wrappers (Phase 2 wires these into the tool registry) ──
def nexi_forge_tool(spec: str = "", **_) -> dict:
    return forge_tool(spec)


def nexi_list_forged_tools(**_) -> dict:
    tools = tool_installer.list_forged()
    return {"ok": True, "tools": tools, "message": f"{len(tools)} forged tool(s): {', '.join(tools) or 'none'}"}


def nexi_remove_tool(name: str = "", **_) -> dict:
    ok = tool_installer.remove(name)
    return {"ok": ok, "message": f"Removed '{name}'." if ok else f"No forged tool named '{name}'."}
