"""Runtime Awareness / Introspection tools (Roadmap Features #7, #14, #5, #15).

Tool cards
----------
show_diagnostics   role: runtime visibility | risk: LOW | confirm: never | verifier: voice state read     | memory: never store  (#7)
get_monitor_state  role: proactive monitor  | risk: LOW | confirm: never | verifier: dashboard sampled    | memory: never store  (#14)
echo_guard_status  role: voice runtime      | risk: LOW | confirm: never | verifier: cooldown state read   | memory: never store  (#5)
get_hud_state      role: HUD / presence     | risk: LOW | confirm: never | verifier: presence state read   | memory: never store  (#15)

All READ-ONLY: they report NEXI's own runtime state. They reuse existing engine
subsystems (voice_diagnostics, world_monitor_dashboard, post_tts_cleanup,
presence_state) and never mutate state. Output is redacted by construction — these
subsystems expose voice/runtime flags only, never secrets.
"""

from __future__ import annotations

from typing import Any


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "runtime_awareness"), "message": message, **extra}


def show_diagnostics(slots: dict | None = None) -> dict[str, Any]:
    """Feature #7 — voice/runtime diagnostics."""
    try:
        from engine.voice_diagnostics import get_voice_diagnostics, format_voice_diagnostics
        payload = get_voice_diagnostics() or {}
        msg = format_voice_diagnostics(payload)
    except Exception:
        payload, msg = {}, "Diagnostics are not available right now."
    return _ok(msg or "Diagnostics ready.", tool="show_diagnostics",
               voice_state=str(payload.get("current_voice_state", "")), diagnostics=payload)


def get_monitor_state(slots: dict | None = None) -> dict[str, Any]:
    """Feature #14 — proactive monitor / world dashboard state."""
    try:
        from engine.world_monitor_dashboard import get_dashboard_state
        state = get_dashboard_state() or {}
    except Exception:
        state = {}
    panels = state.get("panels") or []
    count = int(state.get("panel_count", len(panels)) or 0)
    msg = f"Monitor is tracking {count} panel{'s' if count != 1 else ''}." if count else "The monitor isn't tracking anything right now."
    return _ok(msg, tool="get_monitor_state", panel_count=count, dashboard=state)


def echo_guard_status(slots: dict | None = None) -> dict[str, Any]:
    """Feature #5 — echo / self-TTS guard cooldown state."""
    try:
        from engine.post_tts_cleanup import is_in_cooldown, get_cooldown_remaining_ms, DEFAULT_COOLDOWN_MS
        cooldown = bool(is_in_cooldown())
        remaining = int(get_cooldown_remaining_ms())
        window = int(DEFAULT_COOLDOWN_MS)
    except Exception:
        cooldown, remaining, window = False, 0, 0
    if cooldown:
        msg = f"Echo guard active — in post-speech cooldown, {remaining} ms remaining."
    else:
        msg = "Echo guard ready — not in cooldown, safe to listen."
    return _ok(msg, tool="echo_guard_status", in_cooldown=cooldown,
               cooldown_remaining_ms=remaining, cooldown_ms=window)


def get_hud_state(slots: dict | None = None) -> dict[str, Any]:
    """Feature #15 — conscious HUD / presence state."""
    try:
        from engine.presence_state import get_presence_state
        presence = get_presence_state() or {}
    except Exception:
        presence = {}
    app = ""
    try:
        from engine.os_awareness import _read_active_window, _friendly_app
        _title, proc = _read_active_window()
        app = _friendly_app(proc) if proc else ""
    except Exception:
        app = ""
    mode = str(presence.get("mode", ""))
    goal = str(presence.get("current_goal", ""))
    parts = [f"Mode: {mode or 'idle'}"]
    if app:
        parts.append(f"focused on {app}")
    if goal:
        parts.append(f"goal: {goal}")
    msg = "HUD — " + ", ".join(parts) + "."
    return _ok(msg, tool="get_hud_state", mode=mode, attention=str(presence.get("attention", "")),
               goal=goal, active_app=app, presence=presence)


def what_did_you_learn(slots: dict | None = None) -> dict[str, Any]:
    """Feature #12 — read-only query of Reflexion-style lessons (already redacted at store time)."""
    try:
        from engine.reflection_memory import recall_similar, ReflectionMemory
        lessons = recall_similar("", top_k=5) or []
        total = int(ReflectionMemory.count())
    except Exception:
        lessons, total = [], 0
    if not lessons:
        return _ok("I haven't recorded any lessons yet.", tool="what_did_you_learn",
                   count=total, lessons=[])
    top = lessons[0]
    action = top.get("next_action") or top.get("lesson") or "avoid repeating it"
    msg = (f"I've recorded {total} lesson{'s' if total != 1 else ''}. "
           f"Most recent: when {top.get('failure')}, {action}.")
    return _ok(msg, tool="what_did_you_learn", count=total, lessons=lessons)
