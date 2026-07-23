# ui_loader.py
#
# Loads the appropriate Eel UI directory based on NEXI_UI_MODE env var.
# Supports legacy (www/) and Mark-style (www_mark/) UI modes.
# Safe fallback: if www_mark is missing, falls back to www (legacy).

from __future__ import annotations

import os

_ALLOWED_MODES = {"legacy", "mark"}


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_ui_mode() -> str:
    mode = (os.getenv("NEXI_UI_MODE") or "").strip().lower()
    if mode not in _ALLOWED_MODES:
        return "legacy"
    return mode


def get_ui_dir() -> str:
    mode = get_ui_mode()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    legacy_dir = os.path.join(root, "www")
    mark_dir = os.path.join(root, "www_mark")
    preferred = mark_dir if mode == "mark" else legacy_dir
    fallback = legacy_dir if mode == "mark" else mark_dir
    if os.path.isfile(os.path.join(preferred, "index.html")):
        return preferred
    if os.path.isfile(os.path.join(fallback, "index.html")):
        print(f"[UI_LOADER] {os.path.basename(preferred)} not found, falling back to {os.path.basename(fallback)}", flush=True)
        return fallback
    return preferred


def init_eel_ui(eel_module) -> str:
    dir_name = os.path.basename(get_ui_dir())
    eel_module.init(dir_name)
    print(f"[UI_LOADER] mode={get_ui_mode()} dir={dir_name}", flush=True)
    # Wire the provider-neutral runtime bridge when any agent backend is opted in.
    try:
        from engine.agent_runtime import registry as runtime_registry
        from engine.agent_runtime.session import register_eel as register_agent_runtime_eel
        provider = runtime_registry.selected_provider_id()
        if runtime_registry.runtime_enabled(provider):
            register_agent_runtime_eel(eel_module)
            print(f"[UI_LOADER] agent_runtime bridge registered provider={provider}", flush=True)
    except Exception as exc:
        print(f"[UI_LOADER] agent_runtime bridge skipped reason={type(exc).__name__}", flush=True)
    return dir_name


def should_open_fullscreen() -> bool:
    return _env_bool("NEXI_FULLSCREEN", True)


def get_window_mode() -> str:
    mode = (os.getenv("NEXI_WINDOW_MODE", "fullscreen") or "fullscreen").strip().lower()
    if mode not in {"fullscreen", "maximized", "normal"}:
        return "fullscreen" if should_open_fullscreen() else "normal"
    if should_open_fullscreen() and mode == "normal":
        return "fullscreen"
    return mode


def edge_window_args() -> list[str]:
    mode = get_window_mode()
    if mode == "fullscreen":
        return ["--start-fullscreen"]
    if mode == "maximized":
        return ["--start-maximized"]
    return []


def _mark_ui_exists() -> bool:
    mark_dir = os.path.join(os.path.dirname(__file__), "..", "www_mark")
    return os.path.isdir(mark_dir) and os.path.isfile(os.path.join(mark_dir, "index.html"))
