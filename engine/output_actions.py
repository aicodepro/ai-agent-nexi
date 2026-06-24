from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from engine.memory_safety import is_safe_to_store, redact_sensitive


OUTPUT_DIR = Path(os.environ.get("JARVIS_OUTPUT_DIR") or (Path.home() / "Documents" / "Jarvis Outputs"))
_latest_output: dict = {}


def sanitize_filename(name: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*]+", "_", str(name or "").strip().strip("."))
    value = re.sub(r"\s+", " ", value).strip()
    return (value or "jarvis-output")[:120]


def set_latest_output(content, title="Jarvis Output", content_type="text", summary=""):
    global _latest_output
    text = redact_sensitive(str(content or ""))
    safe, _reason = is_safe_to_store(text[:500])
    if not safe:
        text = "[Content withheld because it may contain sensitive data.]"
    _latest_output = {
        "id": datetime.now().strftime("out_%Y%m%d_%H%M%S"),
        "content": text,
        "title": str(title or "Jarvis Output")[:120],
        "content_type": str(content_type or "text"),
        "summary": str(summary or "")[:500],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    print(f"[OUTPUT] latest_output_saved id={_latest_output['id']}", flush=True)
    return dict(_latest_output)


def get_latest_output():
    return dict(_latest_output)


def copy_latest_output():
    output = get_latest_output()
    content = output.get("content", "")
    if not content:
        return {"ok": False, "message": "There is no output to copy yet."}
    try:
        import pyperclip
        pyperclip.copy(content)
    except Exception:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(content)
            root.update()
            root.destroy()
        except Exception:
            return {"ok": False, "message": "I couldn't access the clipboard."}
    print(f"[OUTPUT] copied_to_clipboard chars={len(content)}", flush=True)
    return {"ok": True, "message": "Copied."}


def _extension_for(output: dict, extension: str | None = None) -> str:
    if extension:
        return extension if extension.startswith(".") else "." + extension
    ctype = str(output.get("content_type") or "text").lower()
    if ctype in {"essay", "report", "markdown", "search"}:
        return ".md"
    if ctype == "code":
        content = output.get("content", "")
        if "<html" in content.lower():
            return ".html"
        if "function " in content or "const " in content:
            return ".js"
        if "def " in content or "import " in content:
            return ".py"
    return ".txt"


def create_output_file(filename=None, extension=".md"):
    output = get_latest_output()
    if not output.get("content"):
        return {"ok": False, "message": "There is no output to save yet."}
    if not filename:
        print("[OUTPUT] filename_required=true", flush=True)
        return {"ok": False, "requires_filename": True, "message": "What should I name the file?"}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clean = sanitize_filename(filename)
    ext = _extension_for(output, extension)
    if not Path(clean).suffix:
        clean += ext
    target = (OUTPUT_DIR / clean).resolve()
    if target.exists():
        print("[OUTPUT] overwrite_confirmation_required=true", flush=True)
        return {"ok": False, "requires_confirmation": True, "message": "That file already exists."}
    target.write_text(output["content"], encoding="utf-8")
    print(f"[OUTPUT] file_created path={target.name}", flush=True)
    return {"ok": True, "message": "File created.", "path": str(target)}


def save_latest_output_as(filename):
    output = get_latest_output()
    return create_output_file(filename=filename, extension=_extension_for(output, None))


def reopen_latest_output():
    output = get_latest_output()
    if not output.get("content"):
        return {"ok": False, "message": "There is no output to show yet."}
    return {"ok": True, "message": "Showing the latest output.", "output": output}


def summarize_latest_output(max_chars: int = 240) -> str:
    output = get_latest_output()
    return (output.get("summary") or output.get("content") or "")[:max_chars]
