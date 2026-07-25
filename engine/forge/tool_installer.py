"""Persist accepted forged tools and load/call them.

A forged tool is a module file under the forge dir plus a JSON metadata sidecar.
The forge dir is overridable via NEXI_FORGE_DIR (used by tests).

call_forged() runs an accepted tool in-process — only ever reached for tools that
passed the static scan (Phase 1 installs SAFE tools only) and, later, the approval
gate. Registered tools still route through nexi_tool_proxy at call time.
"""
import importlib.util
import json
import keyword
import os
import re
from pathlib import Path


def _forge_dir() -> str:
    return os.environ.get("NEXI_FORGE_DIR") or os.path.join(os.path.dirname(__file__), "custom_tools")


def sanitize_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(name or "")).strip("_")[:64]
    if safe and safe[0].isdigit():
        safe = f"_{safe}"
    if keyword.iskeyword(safe):
        safe = f"{safe}_tool"
    if not safe or not safe.isidentifier():
        raise ValueError("Forged tool name must resolve to a valid Python identifier.")
    return safe


def _tool_path(name: str, suffix: str) -> Path:
    directory = Path(_forge_dir()).expanduser().resolve()
    path = (directory / f"{sanitize_name(name)}{suffix}").resolve()
    if path.parent != directory:
        raise ValueError("Forged tool path must stay inside custom_tools.")
    return path


def install(name: str, function_code: str, metadata: dict | None = None) -> str:
    """Write the tool module + metadata sidecar. Returns the module path."""
    safe_name = sanitize_name(name)
    directory = Path(_forge_dir()).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = _tool_path(safe_name, ".py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(function_code)
    meta = dict(metadata or {})
    meta["name"] = safe_name
    with open(_tool_path(safe_name, ".json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return str(path)


def list_forged() -> list[str]:
    directory = _forge_dir()
    if not os.path.isdir(directory):
        return []
    return sorted(
        n[:-3] for n in os.listdir(directory)
        if n.endswith(".py") and n != "__init__.py"
    )


def remove(name: str) -> bool:
    removed = False
    for ext in (".py", ".json"):
        path = _tool_path(name, ext)
        if os.path.exists(path):
            os.remove(path)
            removed = True
    return removed


def call_forged(name: str, *args, **kwargs):
    """Dynamically import a forged tool module and call its `name` function."""
    safe_name = sanitize_name(name)
    path = _tool_path(safe_name, ".py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"forged tool not found: {safe_name}")
    spec = importlib.util.spec_from_file_location(f"forged_{safe_name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, safe_name, None)
    if fn is None:
        raise AttributeError(f"forged tool '{safe_name}' has no function named '{safe_name}'")
    return fn(*args, **kwargs)
