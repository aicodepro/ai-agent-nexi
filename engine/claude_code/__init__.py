"""Nexi × Claude Code — Nexi drives the Claude Code CLI (headless, auto mode,
scoped to a project) and verifies the result to catch hallucinations. Original
Nexi code. See docs/superpowers/specs/2026-07-13-nexi-claude-code-design.md.
"""
from engine.claude_code.dispatcher import is_enabled, stop
from engine.claude_code.session import (
    nexi_code_stop,
    nexi_code_task,
    register_eel,
    run_task,
)

__all__ = [
    "run_task", "stop", "is_enabled",
    "nexi_code_task", "nexi_code_stop", "register_eel",
]
