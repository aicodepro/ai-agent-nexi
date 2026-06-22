"""File system control actions."""

import os
from pathlib import Path

SAFE_DIRS = {
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
}


def _is_safe_path(path: Path) -> bool:
    resolved = path.resolve()
    return any(str(resolved).startswith(str(sd)) for sd in SAFE_DIRS)


def handle_create_folder(entity: str) -> dict:
    path = Path.home() / "Desktop" / entity.strip()
    if not _is_safe_path(path):
        return {"ok": False, "message": "Path is outside safe directories."}
    try:
        path.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "message": f"Created: {path}"}
    except Exception as e:
        return {"ok": False, "message": f"Failed: {e}"}


def handle_create_file(entity: str) -> dict:
    path = Path.home() / "Desktop" / entity.strip()
    if not _is_safe_path(path):
        return {"ok": False, "message": "Path is outside safe directories."}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return {"ok": True, "message": f"Created: {path}"}
    except Exception as e:
        return {"ok": False, "message": f"Failed: {e}"}


def handle_open_folder(entity: str) -> dict:
    path = Path.home() / "Desktop" / entity.strip()
    if path.is_dir():
        os.startfile(str(path))
        return {"ok": True, "message": f"Opened: {path}"}
    return {"ok": False, "message": f"Folder not found: {path}"}


def register_file_controls(registry):
    registry.register("create_folder", handle_create_folder, risk="safe")
    registry.register("create_file", handle_create_file, risk="safe")
    registry.register("open_folder", handle_open_folder, risk="safe")
