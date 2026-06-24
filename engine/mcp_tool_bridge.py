from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    message: str
    data: dict[str, Any]
    error_code: str = ""


READ_ONLY_TOOLS = {
    "memory.recall",
    "memory.summary",
    "local_skills.list",
}

FORBIDDEN_KEYWORDS = (
    "delete",
    "remove",
    "write",
    "edit",
    "move",
    "shell",
    "bash",
    "powershell",
    "cmd",
    "run",
    "execute",
    "open_app",
    "email",
    "message.send",
)


def is_tool_allowed(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    if name in READ_ONLY_TOOLS:
        return True
    return False


def blocked_tool_result(tool_name: str) -> ToolResult:
    return ToolResult(
        ok=False,
        message="Tool blocked. Jarvis can only expose read-only context to the brain.",
        data={"tool": (tool_name or "").strip()},
        error_code="TOOL_BLOCKED",
    )


def execute_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
    name = (tool_name or "").strip().lower()
    if not is_tool_allowed(name) or any(word in name for word in FORBIDDEN_KEYWORDS):
        return blocked_tool_result(name)

    if name == "memory.recall":
        from engine.memory_store import recall
        return ToolResult(True, "Memory recalled.", {"text": recall()})
    if name == "memory.summary":
        from engine.memory_store import get_brain_memory_context
        return ToolResult(True, "Memory summary ready.", {"text": get_brain_memory_context()})
    if name == "local_skills.list":
        return ToolResult(
            True,
            "Local skills listed.",
            {"skills": ["open app", "open website", "web search", "screenshot", "note", "create file", "create project folder"]},
        )

    return blocked_tool_result(name)
