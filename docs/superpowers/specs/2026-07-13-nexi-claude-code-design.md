# Nexi × Claude Code — orchestration layer (2026-07-13)

## Goal
Nexi = the intelligent layer (interprets, dispatches, verifies). Claude Code = the
code-writing engine, run **headless in auto mode**, **scoped to a project dir**, and
**you trigger every task**. Original Nexi code; drives the installed `claude` CLI (2.1.207).

Decisions: run all phases together. Auto mode (`--permission-mode acceptEdits` default,
`--dangerously-skip-permissions` opt-in). Embedded terminal panel to watch/verify + STOP.
Anti-hallucination verification after each run. Opt-in via `NEXI_CLAUDE_CODE_ENABLED=1`.

## Components (engine/claude_code/)
- `dispatcher.py` — `dispatch(task, project_dir, on_event)`: runs
  `claude -p <task> --output-format stream-json --verbose --add-dir <dir> --append-system-prompt <guardrails> <permission-args>`
  as a subprocess; parses newline-delimited JSON events, streams them to `on_event`, captures the
  final `result`. `stop()` kills the run. Enabled/permission via env.
- `verifier.py` — anti-hallucination: `git diff --stat` (did it actually change anything?),
  optional test run (`pytest`), optional second-model verdict. Returns `{on_track, checks}`.
- `terminal_bridge.py` — optional true-PTY backend (pywinpty) for a fully interactive terminal.
- `session.py` — orchestrator: `run_task(task, project_dir, verify=True)` = dispatch → verify →
  combined result. Exposes `nexi_code_task` / `nexi_code_stop` tool wrappers + eel bridge functions
  (`claude_code_start/stop/input`, pushes events to the UI).
- UI (`www_mark/`): a monospace "Claude Code" panel that streams events live, with an input box and
  a STOP button. Original code (no third-party terminal lib), works offline; a full xterm.js/ANSI
  terminal is a later upgrade (needs the lib vendored).

## Safety (auto mode)
Scoped to the target project (`--add-dir`, not the whole disk); opt-in env flag; STOP/kill; guardrail
system-prompt ("stay on task, don't invent APIs, run tests, admit uncertainty"); verification pass.
Default permission mode `acceptEdits` (auto-accepts edits, won't silently run destructive shell cmds).

## Testing
Dispatcher tested with a **mocked `claude` process** (fake stream-json, no tokens). Verifier tested
with mocked git/pytest. Session tested with dispatcher+verifier mocked. The browser UI panel and the
pywinpty bridge are compile/lint-checked but need the live eel UI + a real run to validate on-device.
