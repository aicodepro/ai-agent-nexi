"""One atomic reset of transient session state on a new session/connection.

The audit found per-module resets existed but no single on-new-session hook that
clears them together. This is that hook. Each reset is guarded so one failure
never blocks the others. Call from app startup and from session managers on a
fresh wake/conversation session.
"""
import importlib

# (module, module-level reset function) — confirmed to exist.
_RESETS = [
    ("engine.workflow_state", "clear_workflow"),
    ("engine.conversation_context", "clear_recent_context"),
    ("engine.app.runtime_context", "reset_runtime"),
    ("engine.barge_in_manager", "reset_barge_in_state"),
    ("engine.post_tts_cleanup", "reset_cooldown"),
    ("engine.presence_state", "reset_presence_state"),
    # keeps environment/working_memory (still true), clears last_action/current_step
    ("engine.world_model", "reset_world"),
]


def reset_session():
    """Run every registered per-module reset. Returns the list that actually ran."""
    done = []
    for mod_name, fn_name in _RESETS:
        try:
            mod = importlib.import_module(mod_name)
            getattr(mod, fn_name)()
            done.append(f"{mod_name}.{fn_name}")
        except Exception:
            pass  # a missing/failing reset never blocks the rest
    return done
