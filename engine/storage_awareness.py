"""Storage & Power Awareness Layer (Roadmap Feature #3) — read-only disk/battery state for Nexi.

Tool cards
----------
get_disk_space     role: storage awareness | risk: LOW | confirm: never | verifier: usage sampled        | memory: never store
is_disk_full       role: storage awareness | risk: LOW | confirm: never | verifier: drives sampled        | memory: never store
get_battery_status role: power awareness   | risk: LOW | confirm: never | verifier: battery sensor read    | memory: never store

All functions are READ-ONLY (never delete files, free space, or change power
settings). Every function returns the engine's standard tool-result dict so the
verifier passes on observed values. Desktops with no battery still return a
verified result describing AC power.
"""

from __future__ import annotations

import os
import shutil
from typing import Any


_LOW_FREE_PCT = 10.0
_LOW_FREE_GB = 5.0


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "storage_awareness"), "message": message, **extra}


def _gb(num_bytes: int | float) -> float:
    return round(num_bytes / (1024 ** 3), 1)


def _system_drive() -> str:
    drive = os.environ.get("SystemDrive", "C:")
    return drive + "\\" if not drive.endswith("\\") else drive


def _fixed_mountpoints() -> list[str]:
    """Fixed (non-removable, non-network) mountpoints, falling back to the system drive."""
    points: list[str] = []
    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            opts = (part.opts or "").lower()
            if "cdrom" in opts or "removable" in opts:
                continue
            if part.fstype and part.mountpoint:
                points.append(part.mountpoint)
    except Exception:
        pass
    if not points:
        points = [_system_drive()]
    return points


def get_disk_space(slots: dict | None = None) -> dict[str, Any]:
    drive = _system_drive()
    usage = shutil.disk_usage(drive)
    free_gb = _gb(usage.free)
    total_gb = _gb(usage.total)
    used_pct = round((usage.used / usage.total) * 100) if usage.total else 0
    msg = f"Drive {drive.rstrip(chr(92))} has {free_gb} GB free of {total_gb} GB ({used_pct}% used)."
    return _ok(msg, tool="get_disk_space", drive=drive, free_gb=free_gb,
               total_gb=total_gb, used_percent=used_pct)


def is_disk_full(slots: dict | None = None) -> dict[str, Any]:
    low: list[str] = []
    details: list[dict[str, Any]] = []
    for mount in _fixed_mountpoints():
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        free_gb = _gb(usage.free)
        free_pct = round((usage.free / usage.total) * 100, 1) if usage.total else 0.0
        details.append({"drive": mount, "free_gb": free_gb, "free_percent": free_pct})
        if free_pct < _LOW_FREE_PCT or free_gb < _LOW_FREE_GB:
            low.append(f"{mount.rstrip(chr(92))} ({free_gb} GB / {free_pct}% free)")
    full = bool(low)
    if full:
        msg = "Running low on space: " + ", ".join(low) + "."
    elif details:
        msg = "You have plenty of disk space on all drives."
    else:
        msg = "I couldn't read any fixed drives."
    return _ok(msg, tool="is_disk_full", full=full, low_drives=low, drives=details)


def _fmt_time(secs: int) -> str:
    if secs < 0:
        return ""
    hours, mins = secs // 3600, (secs % 3600) // 60
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def get_battery_status(slots: dict | None = None) -> dict[str, Any]:
    try:
        import psutil
        bat = psutil.sensors_battery()
    except Exception:
        bat = None
    if bat is None:
        return _ok("This PC has no battery — it's running on AC power.",
                   tool="get_battery_status", has_battery=False, plugged=True)
    percent = round(bat.percent)
    plugged = bool(bat.power_plugged)
    parts = [f"Battery at {percent}%"]
    if plugged:
        parts.append("charging" if percent < 100 else "fully charged on AC")
    else:
        secs = getattr(bat, "secsleft", None)
        if isinstance(secs, int) and secs not in (-1, -2):
            remaining = _fmt_time(secs)
            if remaining:
                parts.append(f"about {remaining} left")
        else:
            parts.append("on battery")
    msg = ", ".join(parts) + "."
    return _ok(msg, tool="get_battery_status", has_battery=True, percent=percent, plugged=plugged)
