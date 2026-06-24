from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DashboardPanel:
    id: str
    title: str
    data: dict[str, Any]
    priority: int = 0
    refresh_interval: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorldMonitorDashboard:
    """Read-only dashboard aggregator for Nexi runtime state."""

    def get_all_panels(self) -> list[DashboardPanel]:
        panels = [
            self._system_panel(),
            self._memory_panel(),
            self._active_panel(),
            self._tools_panel(),
            self._commands_panel(),
            self._routes_panel(),
            self._brain_panel(),
            self._wake_panel(),
        ]
        return sorted(panels, key=lambda panel: panel.priority, reverse=True)

    def get_panel(self, panel_id: str) -> DashboardPanel | None:
        target = str(panel_id or "").strip().lower()
        for panel in self.get_all_panels():
            if panel.id == target:
                return panel
        return None

    def get_dashboard_state(self) -> dict[str, Any]:
        panels = [panel.to_dict() for panel in self.get_all_panels()]
        return {"version": 1, "updated_at": time.time(), "panels": panels, "panel_count": len(panels)}

    def _system_panel(self) -> DashboardPanel:
        try:
            from engine.diagnostics import Diagnostics, check_all_dict
            data = {"checks": check_all_dict(), "uptime": Diagnostics.get_uptime()}
        except Exception as exc:
            data = {"error": type(exc).__name__}
        return DashboardPanel("system", "System", data, priority=100)

    def _memory_panel(self) -> DashboardPanel:
        data: dict[str, Any] = {}
        try:
            from engine.memory.session_memory import get_session_memory
            data["session_turns"] = get_session_memory().count()
        except Exception:
            data["session_turns"] = 0
        try:
            from engine.memory.episodic_memory import get_episodic_memory
            data["episodes"] = get_episodic_memory().count()
        except Exception:
            data["episodes"] = 0
        try:
            from engine.memory.semantic_memory import get_semantic_memory
            data["semantic_facts"] = get_semantic_memory().count()
        except Exception:
            data["semantic_facts"] = 0
        try:
            from engine.reflection_memory import ReflectionMemory
            data["reflection_lessons"] = ReflectionMemory.count()
        except Exception:
            data["reflection_lessons"] = 0
        return DashboardPanel("memory", "Memory", data, priority=90)

    def _active_panel(self) -> DashboardPanel:
        try:
            from engine.presence_state import get_presence_state
            data = get_presence_state()
        except Exception as exc:
            data = {"error": type(exc).__name__}
        return DashboardPanel("active", "Active Task", data, priority=80)

    def _tools_panel(self) -> DashboardPanel:
        try:
            from engine.tool_registry import registered_tool_names
            names = registered_tool_names()
            data = {"total": len(names), "sample": names[:8]}
        except Exception as exc:
            data = {"error": type(exc).__name__}
        return DashboardPanel("tools", "Tools", data, priority=70)

    def _commands_panel(self) -> DashboardPanel:
        try:
            from engine.conversation_context import get_recent_turns
            turns = get_recent_turns(8)
            data = {"recent": [{"role": turn.get("role", ""), "text": str(turn.get("text", ""))[:120]} for turn in turns]}
        except Exception:
            data = {"recent": []}
        return DashboardPanel("commands", "Commands", data, priority=60)

    def _routes_panel(self) -> DashboardPanel:
        try:
            from engine.intent_explainer import explain_last_intent
            data = {"last": explain_last_intent()[:240]}
        except Exception:
            data = {"last": "No route yet."}
        return DashboardPanel("routes", "Routes", data, priority=50)

    def _brain_panel(self) -> DashboardPanel:
        data = {
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
            "intent_model": os.getenv("GROQ_INTENT_MODEL", "openai/gpt-oss-20b"),
            "react_model": os.getenv("REACT_MODEL", os.getenv("GROQ_INTENT_MODEL", "openai/gpt-oss-20b")),
        }
        return DashboardPanel("brain", "Brain", data, priority=40)

    def _wake_panel(self) -> DashboardPanel:
        data = {
            "wake_backend": os.getenv("VOICE_WAKE_BACKEND", "openwakeword"),
            "hotword_threshold": os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.25"),
            "clap_primary": os.getenv("NEXI_CLAP_PRIMARY", "dsp_clap"),
            "clap_cooldown_ms": os.getenv("NEXI_CLAP_COOLDOWN_MS", "1500"),
        }
        return DashboardPanel("wake", "Wake", data, priority=30)


def get_dashboard_state() -> dict[str, Any]:
    return WorldMonitorDashboard().get_dashboard_state()
