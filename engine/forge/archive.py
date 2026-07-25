"""Idea #83 — every self-modification archived, one-command rollback.

The DGM pattern: a self-improving system must keep an ARCHIVE of versions, not a single
mutable lineage, so any change can be reverted the moment it turns out to be worse. Forge
previously had `install` / `remove` and no history at all — if a forged tool regressed,
the old working version was simply gone.

Two deliberate placements:

  * the archive lives OUTSIDE the directory Forge installs into, so a forged tool cannot
    delete the evidence of what it replaced (idea #84: never let the agent write to its
    own gate or its own history);
  * every version is stored with the scan + verdict that let it in, so a rollback also
    tells you WHY the bad version was accepted — otherwise the same mistake returns.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path


def archive_root() -> Path:
    raw = (os.getenv("NEXI_FORGE_ARCHIVE") or "").strip()
    if raw:
        return Path(raw)
    # NOT under custom_tools/ — Forge installs there and must not own its own history.
    return Path(__file__).resolve().parents[2] / "data" / "forge_archive"


def _tool_dir(name: str) -> Path:
    safe = "".join(c for c in str(name) if c.isalnum() or c in "_-")[:64] or "unnamed"
    return archive_root() / safe


def _index_path(name: str) -> Path:
    return _tool_dir(name) / "index.json"


def _read_index(name: str) -> list[dict]:
    p = _index_path(name)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_index(name: str, entries: list[dict]) -> None:
    p = _index_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def record(name: str, source: str, *, verdict: dict | None = None,
           scan: dict | None = None, spec: str = "") -> dict:
    """Archive a version of a forged tool. Returns the archive entry."""
    digest = hashlib.sha256(str(source or "").encode("utf-8")).hexdigest()
    entries = _read_index(name)
    version = len(entries) + 1
    blob = _tool_dir(name) / f"v{version:04d}.py"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_text(str(source or ""), encoding="utf-8")
    entry = {
        "version": version,
        "sha256": digest,
        "path": str(blob),
        "at": time.time(),
        "spec": str(spec)[:500],
        # keep WHY it was accepted, so a rollback explains the mistake too
        "verdict": {k: verdict.get(k) for k in ("ok", "reason", "holdout_cases", "holdout_passed")}
        if isinstance(verdict, dict) else None,
        "scan_safe": bool((scan or {}).get("safe")) if isinstance(scan, dict) else None,
    }
    entries.append(entry)
    _write_index(name, entries)
    print(f"[FORGE_ARCHIVE] {name} v{version} sha={digest[:12]}", flush=True)
    return entry


def history(name: str) -> list[dict]:
    return _read_index(name)


def versions(name: str) -> int:
    return len(_read_index(name))


def get_source(name: str, version: int | None = None) -> str | None:
    """Source of a specific version (default: latest)."""
    entries = _read_index(name)
    if not entries:
        return None
    entry = entries[-1] if version is None else next(
        (e for e in entries if int(e.get("version", 0)) == int(version)), None)
    if not entry:
        return None
    try:
        return Path(entry["path"]).read_text(encoding="utf-8")
    except Exception:
        return None


def rollback(name: str, *, to_version: int | None = None, install_fn=None) -> dict:
    """Revert a forged tool to a previous archived version — the one command #83 wants.

    Defaults to the version BEFORE the current one (undo the last change).
    """
    entries = _read_index(name)
    if len(entries) < 2 and to_version is None:
        return {"ok": False, "name": name, "versions": len(entries),
                "message": f"'{name}' has no earlier version to roll back to."}
    target = int(to_version) if to_version is not None else int(entries[-2]["version"])
    source = get_source(name, target)
    if source is None:
        return {"ok": False, "name": name, "message": f"Archived version {target} is unreadable."}

    if install_fn is None:
        from engine.forge import tool_installer
        install_fn = tool_installer.install
    try:
        path = install_fn(name, source, {"rolled_back_to": target, "reason": "manual_rollback"})
    except Exception as exc:
        return {"ok": False, "name": name, "message": f"Rollback failed: {type(exc).__name__}"}

    # A rollback is itself a new version, so history stays append-only and auditable.
    record(name, source, spec=f"rollback to v{target}")
    return {"ok": True, "name": name, "restored_version": target, "path": str(path),
            "message": f"Rolled '{name}' back to archived version {target}."}


def purge(name: str | None = None) -> int:
    """Delete archive history. Tests/manual only — never called by Forge itself."""
    root = archive_root()
    if name:
        target = _tool_dir(name)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            return 1
        return 0
    if root.exists():
        n = sum(1 for _ in root.iterdir())
        shutil.rmtree(root, ignore_errors=True)
        return n
    return 0


def _demo() -> None:
    os.environ["NEXI_FORGE_ARCHIVE"] = str(
        Path(os.getenv("TEMP", "/tmp")) / "nexi_forge_archive_demo")
    purge()
    record("adder", "def add(a,b): return a+b", spec="add two numbers")
    record("adder", "def add(a,b): return a-b", spec="BROKEN change")
    assert versions("adder") == 2
    installed = {}
    res = rollback("adder", install_fn=lambda n, s, m: installed.setdefault(n, s) or "path")
    assert res["ok"] and res["restored_version"] == 1, res
    assert "a+b" in installed["adder"], "did not restore the working version"
    assert versions("adder") == 3, "rollback must be recorded, keeping history append-only"
    purge()
    print("forge archive._demo OK")


if __name__ == "__main__":
    _demo()
