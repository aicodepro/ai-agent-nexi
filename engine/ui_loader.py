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
    if mode == "mark":
        mark_dir = os.path.join(os.path.dirname(__file__), "..", "www_mark")
        if os.path.isdir(mark_dir) and os.path.isfile(os.path.join(mark_dir, "index.html")):
            return mark_dir
        print(f"[UI_LOADER] www_mark not found, falling back to www", flush=True)
    return os.path.join(os.path.dirname(__file__), "..", "www")


def init_eel_ui(eel_module) -> str:
    dir_name = "www_mark" if get_ui_mode() == "mark" and _mark_ui_exists() else "www"
    eel_module.init(dir_name)
    print(f"[UI_LOADER] mode={get_ui_mode()} dir={dir_name}", flush=True)
    # Wire the Claude Code terminal bridge (only when the feature is opted in).
    try:
        from engine.claude_code import is_enabled, register_eel
        if is_enabled():
            register_eel(eel_module)
            print("[UI_LOADER] claude_code bridge registered", flush=True)
    except Exception as exc:
        print(f"[UI_LOADER] claude_code bridge skipped reason={type(exc).__name__}", flush=True)
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
