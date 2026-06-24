"""File and folder operations."""

import os
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass

INVALID_CHARS = set('<>:"/\\|?*')

TEMPLATES = {
    ".py": '"""Module docstring."""\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
    ".html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Document</title>\n</head>\n<body>\n    \n</body>\n</html>\n',
    ".js": '"use strict";\n\nconsole.log("Hello, world!");\n',
    ".css": "/* Styles */\n\n* {\n    margin: 0;\n    padding: 0;\n    box-sizing: border-box;\n}\n",
    ".tsx": 'import React from "react";\n\nexport default function App() {\n    return <div>Hello</div>;\n}\n',
    ".jsx": 'import React from "react";\n\nexport default function App() {\n    return <div>Hello</div>;\n}\n',
}


def _safe_name(name: str) -> str:
    return "".join(c for c in name.strip() if c not in INVALID_CHARS).strip()


def resolve_location(text: str) -> Path:
    """Map text like 'desktop', 'documents' to filesystem path."""
    lower = text.lower().strip()
    home = Path.home()
    mapping = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "home": home,
    }
    return mapping.get(lower, Path(text) if os.path.isabs(text) else home / "Desktop")


def create_folder(name: str, location: str = "desktop") -> dict:
    safe = _safe_name(name)
    if not safe:
        return {"handled": False, "message": "Invalid folder name."}
    path = resolve_location(location) / safe
    try:
        path.mkdir(parents=True, exist_ok=True)
        return {"handled": True, "message": f"Created folder: {path}"}
    except Exception as e:
        return {"handled": False, "message": f"Failed to create folder: {e}"}


def create_file(name: str, location: str = "desktop", content: str = "") -> dict:
    safe = _safe_name(name)
    if not safe:
        return {"handled": False, "message": "Invalid file name."}
    path = resolve_location(location) / safe
    ext = path.suffix.lower()
    if not content and ext in TEMPLATES:
        content = TEMPLATES[ext]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content or "", encoding="utf-8")
        return {"handled": True, "message": f"Created file: {path}"}
    except Exception as e:
        return {"handled": False, "message": f"Failed to create file: {e}"}


def create_project(name: str, location: str = "desktop",
                   files: list = None) -> dict:
    safe = _safe_name(name)
    if not safe:
        return {"handled": False, "message": "Invalid project name."}
    project_dir = resolve_location(location) / safe
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        created = [str(project_dir)]
        for fname in (files or ["main.py"]):
            fpath = project_dir / fname
            ext = fpath.suffix.lower()
            fpath.write_text(TEMPLATES.get(ext, ""), encoding="utf-8")
            created.append(str(fpath))
        # Try to open in VS Code
        try:
            subprocess.Popen(["code", str(project_dir)], shell=False)
        except Exception as e:
            print(f"[FILES] vs_code_open_failed: {e}", flush=True)
        return {"handled": True, "message": f"Created project: {project_dir}",
                "files": created}
    except Exception as e:
        return {"handled": False, "message": f"Failed to create project: {e}"}


def take_screenshot() -> dict:
    try:
        import pyautogui
        from datetime import datetime
        path = Path.home() / "Desktop" / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        img = pyautogui.screenshot()
        img.save(str(path))
        return {"handled": True, "message": f"Screenshot saved: {path}"}
    except Exception as e:
        return {"handled": False, "message": f"Screenshot failed: {e}"}
