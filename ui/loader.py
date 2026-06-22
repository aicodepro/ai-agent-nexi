"""UI loader — Eel initialization and window management."""

import os
from pathlib import Path
from core.config import cfg

UI_DIR = Path(__file__).resolve().parent.parent / "www"


def init_eel(eel_module):
    if not UI_DIR.exists():
        raise FileNotFoundError(f"UI directory not found: {UI_DIR}")
    eel_module.init(str(UI_DIR))
    print(f"[UI] initialized dir={UI_DIR}", flush=True)


def edge_window_args() -> list:
    mode = cfg.window_mode
    if mode == "fullscreen":
        return ["--start-fullscreen"]
    elif mode == "maximized":
        return ["--start-maximized"]
    return []


def should_open_fullscreen() -> bool:
    return cfg.fullscreen
