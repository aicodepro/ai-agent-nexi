# Nexi Forge — self-development tool-forging loop (2026-07-13)

## Goal
Let Nexi turn a capability request into a **new, callable tool** — but only after an
auto-generated **test proves it runs**. Original Nexi code; Ada-SI / Hermes are the
*reference pattern* only (no third-party code copied, no third-party branding).

Decisions (from brainstorming):
- **Scope**: forge NEW tools only; never edit Nexi's core code.
- **Triggers**: explicit ("build a tool that…") + opt-in auto-forge on a capability gap (`NEXI_FORGE_AUTO=1`, default off).
- **Accept gate**: SAFE (compute/read only) auto-registers on test pass; RISKY (touches fs/network/subprocess) needs user approval via the existing `approval_queue`.
- **Model-agnostic**: code generation goes through an injectable generator (default = Nexi's brain); user connects whatever model.

## The loop (data flow)
```
request → code_generator (LLM) → {name, function_code, test_code}
        → safety_scan (AST: fs/network/subprocess/exec?) → classify safe|risky
        → sandbox_runner (subprocess pytest, timeout, no main-process access)
        → passed? — no → feed error back to generator, retry (max N) → else give up
             │ yes
        → accept_gate (safe→auto | risky→approval_queue)
        → tool_installer (persist to engine/forge/custom_tools/<name>.py + metadata json)
        → callable (loader); still routes through nexi_tool_proxy at call time
```

## Components (small, isolated, each unit-tested)
- `engine/forge/safety_scan.py` — `scan(code) -> {safe, flags, reason}`. Pure AST analysis; conservative (pure compute = safe; any fs/network/subprocess/exec = risky).
- `engine/forge/sandbox_runner.py` — `run_test(function_code, test_code, timeout) -> {passed, output}`. Writes both to a temp dir, runs `python -m pytest` in a subprocess (timeout + CREATE_NO_WINDOW), cleans up.
- `engine/forge/code_generator.py` — `generate(spec, generate_fn=None) -> {name, function_code, test_code}`. `generate_fn` injectable (default = Nexi brain); fake in tests.
- `engine/forge/accept_gate.py` — `decide(scan_result) -> "auto" | "approve"`.
- `engine/forge/tool_installer.py` — `install(name, code, metadata) -> path`; `list_forged()`, `remove(name)`, `call_forged(name, **kw)` (dynamic import).
- `engine/forge/forge_engine.py` — `forge_tool(spec, generate_fn=None, max_retries=2) -> result`. Orchestrates the loop; exposes `nexi_forge_tool` / `nexi_list_forged_tools` / `nexi_remove_tool`.

## Safety (non-negotiable)
- Generated code executes **only** in the sandbox subprocess until accepted — never in the main process.
- Static scan gates execution classification; risky tools require approval.
- Subprocess has a hard timeout; forged tools are listable/removable; core code is never touched.
- Registered tools still pass through `nexi_tool_proxy` risk-gating at call time.
- **Ceiling (ponytail)**: no OS-level/container sandbox in Phase 1 — safety = static-scan + subprocess-timeout. Untrusted/risky auto-execution would need a container; that's the upgrade path.

## Phasing
- **Phase 1 (build now)**: generate → scan → sandbox-test → persist → callable via loader. Fake-generator tests + one good tool (forges) + one bad tool (test fails → rejected). Safe tools only.
- **Phase 2**: risky tools via approval gate; wire forged tools into the live intent router so voice commands reach them.
- **Phase 3**: opt-in auto-forge on capability gaps.

## Testing
Each component ships a unit test. Forge loop tested end-to-end with a **fake generator** (deterministic function+test) — no live LLM/network. Never drives real keyboard/mouse (conftest guard holds).
