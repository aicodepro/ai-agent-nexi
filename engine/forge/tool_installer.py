"""Persist accepted forged tools and load/call them.

A forged tool is a module file under the forge dir plus a JSON metadata sidecar.
The forge dir is overridable via NEXI_FORGE_DIR (used by tests).

call_forged() runs an accepted tool in-process — only ever reached for tools that
passed the static scan (Phase 1 installs SAFE tools only) and, later, the approval
gate. Registered tools still route through nexi_tool_proxy at call time.
"""
import importlib.util
import json
import os


def _forge_dir() -> str:
    return os.environ.get("NEXI_FORGE_DIR") or os.path.join(os.path.dirname(__file__), "custom_tools")


def install(name: str, function_code: str, metadata: dict | None = None) -> str:
    """Write the tool module + metadata sidecar. Returns the module path."""
    directory = _forge_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(function_code)
    meta = dict(metadata or {})
    meta["name"] = name
    with open(os.path.join(directory, f"{name}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return path


def list_forged() -> list[str]:
    directory = _forge_dir()
    if not os.path.isdir(directory):
        return []
    return sorted(
        n[:-3] for n in os.listdir(directory)
        if n.endswith(".py") and n != "__init__.py"
    )


def remove(name: str) -> bool:
    directory = _forge_dir()
    removed = False
    for ext in (".py", ".json"):
        path = os.path.join(directory, f"{name}{ext}")
        if os.path.exists(path):
            os.remove(path)
            removed = True
    return removed


def call_forged(name: str, *args, **kwargs):
    """Dynamically import a forged tool module and call its `name` function."""
    path = os.path.join(_forge_dir(), f"{name}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"forged tool not found: {name}")
    spec = importlib.util.spec_from_file_location(f"forged_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, name, None)
    if fn is None:
        raise AttributeError(f"forged tool '{name}' has no function named '{name}'")
    return fn(*args, **kwargs)
