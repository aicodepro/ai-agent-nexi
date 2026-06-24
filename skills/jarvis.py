"""Jarvis skill stubs — Phase 1 foundation. Real implementations in Phases 2-5."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def run_agent(task: str) -> str:
    LOGGER.info("[JARVIS] run_agent task=%s", task)
    return f"Agent task queued: {task}. Full ReAct planner coming in Phase 3."


def execute_tool(tool_name: str) -> str:
    LOGGER.info("[JARVIS] execute_tool name=%s", tool_name)
    return f"Tool execution requested: {tool_name}. Tool registry coming in Phase 2."


def train_on_correction(text: str) -> str:
    LOGGER.info("[JARVIS] train_on_correction text=%s", text)
    return f"Correction noted. Training engine coming in Phase 5."


def add_rule(rule_text: str) -> str:
    LOGGER.info("[JARVIS] add_rule text=%s", rule_text)
    return f"Rule noted: '{rule_text}'. Rule persistence coming in Phase 4."


def remove_rule(rule_text: str) -> str:
    LOGGER.info("[JARVIS] remove_rule text=%s", rule_text)
    return f"Rule removal requested: '{rule_text}'. Coming in Phase 4."


def agent_status() -> str:
    return (
        "NEXI-JARVIS Fusion — Phase 1 foundation active.\n"
        "  Jarvis route:    configured\n"
        "  Tool registry:   Phase 2\n"
        "  ReAct planner:   Phase 3\n"
        "  Advanced memory: Phase 4\n"
        "  Training:        Phase 5"
    )


def reflect() -> str:
    return "Reflection engine coming in Phase 4."


def tool_help(tool_name: str) -> str:
    return f"Help for '{tool_name}': Tool documentation coming in Phase 2."


def cancel_agent() -> str:
    LOGGER.info("[JARVIS] cancel_agent")
    return "Agent cancellation requested. Interrupt handler coming in Phase 3."
