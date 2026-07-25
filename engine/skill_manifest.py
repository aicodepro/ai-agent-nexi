"""Skill Manifest — comprehensive catalog of every capability in the Nexi system.

This module aggregates all sources of truth:
  1. tool_registry — ~120+ registered tools with specs, handlers, aliases
  2. local_skills — OS-level app/website/file operations
  3. mcp_tool_bridge — read-only context bridge for safety-gated MCP tools
  4. agent/skills — Claude Code skills tree (gstack, impeccable, taste, etc.)

The manifest is purely read-only introspection, complementary to
tool_registry.py (execution) and skill_library.py (user-facing catalog).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ── Paths ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_SKILLS_DIR = REPO_ROOT / "agent" / "skills"
PROJECT_SKILLS_DIR = REPO_ROOT / ".opencode" / "skills"
EMPTY_SKILLS_DIR = REPO_ROOT / "skills"
CONFIG_DIR = REPO_ROOT / "config"


# ── Core manifest structure ────────────────────────────────────────────────

def _build_manifest() -> dict[str, Any]:
    """Assemble the full skill manifest from all available sources."""
    tools = _load_tool_registry()
    local = _load_local_skills()
    bridges = _load_mcp_bridge_tools()
    agent_skills = _scan_agent_skills()
    mcp_servers = _load_mcp_servers()

    return {
        "schema_version": "2.0",
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "sources": {
            "tool_registry": {
                "description": "Primary tool execution engine (~120 tools)",
                "count": len(tools),
                "categories": _categorize_tools(tools),
            },
            "local_skills": {
                "description": "OS-interaction skills (apps, websites, files)",
                "count": len(local),
            },
            "mcp_bridge": {
                "description": "Safety-gated MCP bridge tools (read-only)",
                "count": len(bridges),
            },
            "agent_skills": {
                "description": "Claude Code skills tree in agent/skills/",
                "count": len(agent_skills),
                "categories": _categorize_agent_skills(agent_skills),
            },
            "mcp_servers": {
                "description": "Configured MCP server endpoints",
                "count": len(mcp_servers),
            },
        },
        "tools": {
            "by_name": {t["name"]: t for t in tools},
            "by_category": _group_by_category(tools),
        },
        "local_skills": {s["name"]: s for s in local},
        "mcp_bridge_tools": {b["name"]: b for b in bridges},
        "agent_skill_dirs": {s["name"]: s for s in agent_skills},
        "mcp_servers": mcp_servers,
        "total_capabilities": len(tools) + len(local) + len(bridges),
    }


# ── Registry loader ────────────────────────────────────────────────────────

def _load_tool_registry() -> list[dict[str, Any]]:
    """Load all enabled tools from tool_registry via its manifest API."""
    try:
        from engine.tool_registry import router_tool_manifest, registered_tool_names

        cards = router_tool_manifest()
        # enrich with handler info from registry
        names = registered_tool_names()
        return [
            {
                "name": c["name"],
                "description": c.get("description", ""),
                "category": c.get("category", "general"),
                "aliases": c.get("aliases", []),
                "examples": c.get("examples", []),
                "risk_level": c.get("risk_level", "low"),
                "requires_confirmation": c.get("requires_confirmation", False),
                "handler": _resolve_handler(c["name"]),
            }
            for c in cards
            if c["name"] in names
        ]
    except Exception:
        return []


def _resolve_handler(tool_name: str) -> str:
    """Best-effort resolution of a tool name to its handler module path."""
    # Map known tool name prefixes to handler modules
    _handler_map: dict[str, str] = {
        # Local skills
        "open_app": "engine.local_skills.open_app",
        "open_website": "engine.local_skills.open_website",
        "web_search": "engine.local_skills.web_search",
        "create_": "engine.local_skills",
        # Camera / vision
        "camera_": "engine.camera_control",
        "hand_": "engine.camera_control",
        "eye_": "engine.camera_control",
        "face_": "engine.camera_control",
        "gesture_": "engine.camera_control",
        # Memory
        "remember": "engine.memory_store",
        "recall_": "engine.memory_store",
        "forget_": "engine.memory_store",
        "take_note": "engine.memory_store",
        "show_notes": "engine.memory_store",
        # OS awareness
        "get_active_window": "engine.os_awareness",
        "what_am_i_working_on": "engine.os_awareness",
        "get_system_state": "engine.os_awareness",
        "why_is_": "engine.os_awareness",
        "get_running_apps": "engine.os_awareness",
        "get_idle_time": "engine.os_awareness",
        # Network
        "am_i_online": "engine.net_awareness",
        "get_network": "engine.net_awareness",
        "get_ip_": "engine.net_awareness",
        # Storage
        "get_disk_": "engine.storage_awareness",
        "is_disk_": "engine.storage_awareness",
        "get_battery": "engine.storage_awareness",
        # Windows settings
        "open_settings": "engine.windows_settings",
        "open_wifi_": "engine.windows_settings",
        "open_bluetooth_": "engine.windows_settings",
        "open_display_": "engine.windows_settings",
        "open_sound_": "engine.windows_settings",
        "open_microphone_": "engine.windows_settings",
        "open_camera_": "engine.windows_settings",
        "open_startup_": "engine.windows_settings",
        "open_windows_update": "engine.windows_settings",
        # Runtime awareness
        "show_diagnostics": "engine.runtime_awareness",
        "get_monitor_": "engine.runtime_awareness",
        "echo_guard_": "engine.runtime_awareness",
        "get_hud_": "engine.runtime_awareness",
        "what_did_you_learn": "engine.runtime_awareness",
        # App intelligence
        "resolve_app_": "engine.app_intelligence",
        "open_app_for_task": "engine.app_intelligence",
        # Skill library
        "list_skills": "engine.skill_library",
        "describe_skill": "engine.skill_library",
        # Browser intelligence
        "read_current_page": "engine.browser_intelligence",
        "list_browser_tabs": "engine.browser_intelligence",
        "read_browser_console": "engine.browser_intelligence",
        "browser_click": "engine.browser_intelligence",
        "browser_fill": "engine.browser_intelligence",
        # Approval queue
        "pending_approvals": "engine.approval_queue",
        "approve_action": "engine.approval_queue",
        "reject_action": "engine.approval_queue",
        # Feature requests
        "request_feature": "engine.feature_requests",
        "list_feature_requests": "engine.feature_requests",
        # Agency / workflow
        "nexi_": "engine.agency",
        # Computer use
        "screen_read": "engine.computer_use",
        "click_ui_element": "engine.computer_use",
        "type_text": "engine.computer_use",
        # Output workspace
        "_output_": "engine.smart_followup_engine",
        # Features
        "search_youtube": "engine.features",
        "play_youtube": "engine.features",
        # Volume / mute
        "volume_": "engine.control.audio",
        "mute": "engine.control.audio",
        # Sleep / wake
        "sleep": "engine.command",
        "wake": "engine.command",
        # Media / browser hotkeys
        "media_": "engine.tool_registry",
        "browser_new": "engine.tool_registry",
        "browser_close": "engine.tool_registry",
        "browser_refresh": "engine.tool_registry",
        "browser_back": "engine.tool_registry",
        "browser_forward": "engine.tool_registry",
        "browser_history": "engine.tool_registry",
        "browser_fullscreen": "engine.tool_registry",
    }
    for prefix, handler in _handler_map.items():
        if tool_name.startswith(prefix) or prefix in tool_name:
            return handler
    return "engine.tool_registry"


# ── Local skills loader ────────────────────────────────────────────────────

def _load_local_skills() -> list[dict[str, Any]]:
    """Extract static skill definitions from engine.local_skills."""
    try:
        from engine.local_skills import APP_COMMANDS, SITES, FILE_TYPES

        skills = []
        for name in APP_COMMANDS:
            skills.append({
                "name": f"app_{name.replace(' ', '_')}",
                "type": "app_launcher",
                "description": f"Open {name}",
                "trigger": name,
                "handler": "engine.local_skills.open_app",
            })
        for name, url in SITES.items():
            skills.append({
                "name": f"site_{name}",
                "type": "site_shortcut",
                "description": f"Open {name} at {url}",
                "trigger": name,
                "url": url,
                "handler": "engine.local_skills.open_website",
            })
        for ext, dot_ext in FILE_TYPES.items():
            skills.append({
                "name": f"filetype_{ext}",
                "type": "file_type",
                "description": f"Create .{ext} files",
                "extension": dot_ext,
                "handler": "engine.local_skills.create_file",
            })
        return skills
    except Exception:
        return []


# ── MCP bridge loader ──────────────────────────────────────────────────────

def _load_mcp_bridge_tools() -> list[dict[str, Any]]:
    """List tools exposed via the MCP bridge (read-only safety gate)."""
    try:
        from engine.mcp_tool_bridge import READ_ONLY_TOOLS

        return [
            {
                "name": name,
                "type": "mcp_bridge",
                "description": _MCP_BRIDGE_DESCRIPTIONS.get(name, "MCP bridge tool"),
                "access": "read_only",
                "handler": "engine.mcp_tool_bridge.execute_mcp_tool",
            }
            for name in sorted(READ_ONLY_TOOLS)
        ]
    except Exception:
        return []


_MCP_BRIDGE_DESCRIPTIONS: dict[str, str] = {
    "memory.recall": "Recall stored facts from Nexi's memory store",
    "memory.summary": "Get a summary of stored brain memory context",
    "local_skills.list": "List available local skills (apps, websites, notes, files)",
}


# ── Agent skills scanner ───────────────────────────────────────────────────

def _scan_agent_skills() -> list[dict[str, Any]]:
    """Scan agent/skills/ for Claude Code skill directories."""
    if not AGENT_SKILLS_DIR.is_dir():
        return []
    skills = []
    for entry in sorted(AGENT_SKILLS_DIR.iterdir()):
        if entry.is_dir():
            has_skill_md = (entry / "SKILL.md").is_file()
            has_skill_md_tmpl = (entry / "SKILL.md.tmpl").is_file()
            skills.append({
                "name": entry.name,
                "path": str(entry.relative_to(REPO_ROOT)),
                "has_skill_md": has_skill_md,
                "has_skill_md_tmpl": has_skill_md_tmpl,
                "type": "claude_code_skill",
            })
        elif entry.suffix == ".md" and entry.stem.upper() == "SKILL":
            skills.append({
                "name": entry.stem,
                "path": str(entry.relative_to(REPO_ROOT)),
                "type": "flat_skill_md",
            })
    return skills


# ── MCP server config loader ───────────────────────────────────────────────

def _load_mcp_servers() -> dict[str, Any]:
    """Read both root .mcp.json and config/mcp.json for MCP server definitions."""
    servers: dict[str, Any] = {}

    sources = [
        ("root", REPO_ROOT / ".mcp.json"),
        ("config", CONFIG_DIR / "mcp.json"),
    ]

    for label, path in sources:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for name, cfg in data.get("mcpServers", {}).items():
                    if name not in servers:
                        servers[name] = {
                            "name": name,
                            "source": label,
                            "command": cfg.get("command", ""),
                            "args": cfg.get("args", []),
                            "autoStart": cfg.get("autoStart", False),
                            "optional": cfg.get("optional", False),
                            "has_env": bool(cfg.get("env")),
                        }
            except Exception:
                pass

    return servers


# ── Category helpers ───────────────────────────────────────────────────────

def _categorize_tools(tools: list[dict[str, Any]]) -> dict[str, int]:
    cats: dict[str, int] = {}
    for t in tools:
        c = t.get("category", "general")
        cats[c] = cats.get(c, 0) + 1
    return cats


def _categorize_agent_skills(skills: list[dict[str, Any]]) -> dict[str, int]:
    # Simple categorization by first directory level under agent/skills/
    from collections import Counter
    families = Counter()
    for s in skills:
        path = Path(s["path"])
        # e.g. "agent/skills/gstack/browse" -> family = "gstack"
        parts = path.parts
        if len(parts) >= 3 and parts[0] == "agent" and parts[1] == "skills":
            families[parts[2]] += 1
    return dict(families.most_common())


def _group_by_category(tools: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in tools:
        c = t.get("category", "general")
        groups.setdefault(c, []).append(t)
    return groups


# ── Public API ─────────────────────────────────────────────────────────────

_MANIFEST_CACHE: dict[str, Any] | None = None


def get_manifest() -> dict[str, Any]:
    """Get the full skill manifest (cached after first build)."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        _MANIFEST_CACHE = _build_manifest()
    return _MANIFEST_CACHE


def refresh_manifest() -> dict[str, Any]:
    """Force rebuild and return the skill manifest."""
    global _MANIFEST_CACHE
    _MANIFEST_CACHE = _build_manifest()
    return _MANIFEST_CACHE


def get_tool_names() -> list[str]:
    """List all registered tool names (fast, no full build)."""
    try:
        from engine.tool_registry import registered_tool_names
        return registered_tool_names()
    except Exception:
        return []


def get_tool(name: str) -> dict[str, Any] | None:
    """Look up a single tool by name."""
    try:
        from engine.tool_registry import get_tool as _get
        return _get(name)
    except Exception:
        return None


def get_mcp_servers() -> dict[str, Any]:
    """Get configured MCP server definitions."""
    return _load_mcp_servers()


def get_category_tools(category: str) -> list[dict[str, Any]]:
    """List all tools in a given category."""
    manifest = get_manifest()
    return manifest.get("tools", {}).get("by_category", {}).get(category, [])


def get_agent_skill_names() -> list[str]:
    """List all discovered agent skill directories."""
    return [s["name"] for s in _scan_agent_skills()]


def get_total_capabilities() -> int:
    """Get the total count of all discoverable capabilities."""
    return get_manifest().get("total_capabilities", 0)


def summary() -> dict[str, Any]:
    """Quick summary of capabilities (fast, no full build if possible)."""
    try:
        from engine.tool_registry import enabled_tools
        tool_count = len(enabled_tools())
    except Exception:
        tool_count = 0
    try:
        local_count = len(_load_local_skills())
    except Exception:
        local_count = 0
    try:
        bridge_count = len(_load_mcp_bridge_tools())
    except Exception:
        bridge_count = 0
    agent_skills = _scan_agent_skills()
    mcp_servers = _load_mcp_servers()

    return {
        "tool_registry_tools": tool_count,
        "local_skills": local_count,
        "mcp_bridge_tools": bridge_count,
        "agent_skill_directories": len(agent_skills),
        "mcp_servers_configured": len(mcp_servers),
        "mcp_server_names": list(mcp_servers.keys()),
        "agent_skill_names": [s["name"] for s in agent_skills[:20]],
        "total_estimated_capabilities": tool_count + local_count + bridge_count,
    }
