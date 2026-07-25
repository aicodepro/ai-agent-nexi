from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
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

# ── Paths ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_MCP_CONFIG = REPO_ROOT / ".mcp.json"
CONFIG_MCP_PATH = REPO_ROOT / "config" / "mcp.json"


def is_tool_allowed(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    if name in READ_ONLY_TOOLS:
        return True
    return False


def is_forbidden_tool_name(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    if name in {"open_app", "message.send"}:
        return True
    tokens = set(re.findall(r"[a-z0-9]+", name))
    return bool(tokens.intersection({"delete", "remove", "write", "edit", "move", "shell", "bash", "powershell", "cmd", "run", "execute", "email"}))


def blocked_tool_result(tool_name: str) -> ToolResult:
    return ToolResult(
        ok=False,
        message="Tool blocked. Nexi can only expose read-only context to the brain.",
        data={"tool": (tool_name or "").strip()},
        error_code="TOOL_BLOCKED",
    )


def execute_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
    name = (tool_name or "").strip().lower()
    if not is_tool_allowed(name) or is_forbidden_tool_name(name):
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


# ══════════════════════════════════════════════════════════════════════════
# MCP Health Check
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class MCPHealthStatus:
    name: str
    source: str  # "root" or "config"
    command_resolves: bool
    package_exists: bool | None  # None means unknown
    auto_start: bool
    is_optional: bool
    error: str = ""


def _resolve_command(command: str) -> bool:
    """Check if a command is available in the environment."""
    try:
        if sys.platform == "win32":
            # On Windows, use where.exe
            result = subprocess.run(
                ["where", command],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        else:
            result = subprocess.run(
                ["which", command],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
    except Exception:
        return False


@lru_cache(maxsize=64)
def _check_npx_package(package_name: str) -> bool | None:
    """Check if an npm package exists on the registry (via npm view)."""
    try:
        # Strip @scope/version specifiers to get package name
        name = package_name.strip()
        if name.startswith("@"):
            # e.g. "@upstash/context7-mcp" or "@brave/brave-search-mcp-server"
            pass
        # Remove version specifiers: "ruflo@latest" -> "ruflo"
        if "@" in name and not name.startswith("@"):
            name = name.split("@")[0]
        elif name.startswith("@") and name.count("@") > 1:
            # @scope/package@version -> @scope/package
            parts = name.rsplit("@", 1)
            if len(parts) == 2 and parts[1]:
                name = parts[0]

        result = subprocess.run(
            ["cmd", "/c", "npm", "view", name, "version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return None


def _read_mcp_configs() -> list[tuple[str, str, dict[str, Any]]]:
    """Read all MCP server configs from both .mcp.json locations."""
    servers: list[tuple[str, str, dict[str, Any]]] = []

    for label, path in [("root", ROOT_MCP_CONFIG), ("config", CONFIG_MCP_PATH)]:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for name, cfg in data.get("mcpServers", {}).items():
                    servers.append((name, label, cfg))
            except Exception as exc:
                print(f"[MCP_HEALTH] failed to read {path}: {exc}", flush=True)

    return servers


def check_mcp_health() -> list[MCPHealthStatus]:
    """Check health of all configured MCP servers.

    Returns a list of MCPHealthStatus entries describing whether each MCP's
    command resolves, the npm package exists, and the config is well-formed.
    """
    configs = _read_mcp_configs()
    results: list[MCPHealthStatus] = []

    for name, source, cfg in configs:
        command = cfg.get("command", "")
        args = cfg.get("args", [])
        auto_start = cfg.get("autoStart", False)
        is_optional = cfg.get("optional", False)
        error = ""

        # 1. Check if the base command resolves
        command_resolves = _resolve_command(command)

        # 2. For npx-based servers, check if the npm package exists
        package_exists: bool | None = None
        if command == "cmd" and len(args) >= 2 and args[0] == "/c" and args[1] == "npx":
            # Extract package name from npx args
            # Format: cmd /c npx -y <package> [args...]
            npx_args = args[2:]  # skip /c and npx
            if npx_args and npx_args[0] == "-y":
                npx_args = npx_args[1:]
            if npx_args:
                package_name = npx_args[0]
                # Check if it's a local path (headroom.exe)
                if package_name.endswith(".exe") or "\\" in package_name:
                    path = REPO_ROOT / package_name
                    package_exists = path.is_file()
                    if not package_exists:
                        # Try as relative to repo root
                        alt_path = Path(package_name)
                        if not alt_path.is_absolute():
                            alt_path = REPO_ROOT / package_name
                        package_exists = alt_path.is_file()
                else:
                    package_exists = _check_npx_package(package_name)

        # 3. For direct command-based servers (not npx), check the exe
        if command != "cmd":
            # Direct command
            if command.endswith(".exe"):
                path = Path(command)
                if not path.is_absolute():
                    path = REPO_ROOT / command
                package_exists = path.is_file()

        if not command_resolves:
            error = f"Command '{command}' not found in PATH"

        results.append(MCPHealthStatus(
            name=name,
            source=source,
            command_resolves=command_resolves,
            package_exists=package_exists,
            auto_start=auto_start,
            is_optional=is_optional,
            error=error,
        ))

    return results


def validate_mcp_config(verbose: bool = False) -> list[dict[str, Any]]:
    """Validate the structure of all MCP config files.

    Returns a list of issues found (empty = clean).
    """
    issues: list[dict[str, Any]] = []

    for label, path in [("root", ROOT_MCP_CONFIG), ("config", CONFIG_MCP_PATH)]:
        if not path.is_file():
            issues.append({
                "severity": "warning",
                "source": label,
                "message": f"MCP config not found at {path}",
            })
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append({
                "severity": "error",
                "source": label,
                "message": f"Invalid JSON: {e}",
            })
            continue

        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            issues.append({
                "severity": "error",
                "source": label,
                "message": "mcpServers must be a dictionary",
            })
            continue

        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                issues.append({
                    "severity": "error",
                    "source": f"{label}/{name}",
                    "message": "Server config must be a dictionary",
                })
                continue

            if "command" not in cfg:
                issues.append({
                    "severity": "error",
                    "source": f"{label}/{name}",
                    "message": "Missing 'command' field",
                })

            command = cfg.get("command", "")
            if command not in ("cmd", "npx", "node", "python", ".venv\\Scripts\\python.exe"):
                if verbose:
                    issues.append({
                        "severity": "info",
                        "source": f"{label}/{name}",
                        "message": f"Unusual command '{command}'",
                    })

            # Check for hardcoded API keys
            env = cfg.get("env", {})
            if isinstance(env, dict):
                for env_key, env_val in env.items():
                    key_lower = env_key.lower()
                    if any(k in key_lower for k in ("api_key", "apikey", "secret", "token", "password")):
                        if env_val and env_val != "<your_key_here>":
                            issues.append({
                                "severity": "warning",
                                "source": f"{label}/{name}/env/{env_key}",
                                "message": "Possible hardcoded secret in env config",
                            })

    return issues


def mcp_health_summary() -> dict[str, Any]:
    """Generate a human-readable health summary for all MCP servers."""
    statuses = check_mcp_health()
    issues = validate_mcp_config()

    healthy = sum(1 for s in statuses if s.command_resolves and s.package_exists is not False)
    warning = sum(1 for s in statuses if not s.command_resolves or s.package_exists is False)
    total = len(statuses)

    servers_detail = []
    for s in statuses:
        if s.command_resolves and (s.package_exists is True or s.package_exists is None):
            state = "healthy"
        elif s.is_optional:
            state = "optional_unhealthy"
        else:
            state = "unhealthy"
        servers_detail.append({
            "name": s.name,
            "source": s.source,
            "state": state,
            "auto_start": s.auto_start,
            "optional": s.is_optional,
            "error": s.error,
        })

    return {
        "total_servers": total,
        "healthy": healthy,
        "warning": warning,
        "config_issues": len(issues),
        "config_issue_details": issues[:5],  # limit to 5
        "servers": servers_detail,
        "summary_line": f"{healthy}/{total} MCP servers healthy, {len(issues)} config issues",
    }
