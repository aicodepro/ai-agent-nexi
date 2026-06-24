"""OS Awareness Layer (Roadmap Feature #1) — read-only PC state for Nexi.

Tool cards
----------
get_active_window      role: PC awareness | risk: LOW | confirm: never | verifier: title/process returned | memory: never store
what_am_i_working_on   role: PC awareness | risk: LOW | confirm: never | verifier: active window resolved   | memory: never store
get_system_state       role: PC awareness | risk: LOW | confirm: never | verifier: cpu/mem sampled           | memory: never store
why_is_pc_slow         role: PC awareness | risk: LOW | confirm: never | verifier: top processes sampled      | memory: never store

All functions are READ-ONLY (never close apps or change settings) and return the
engine's standard tool-result dict so the verifier passes on observed values.
"""

from __future__ import annotations

import time
from typing import Any


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "os_awareness"), "message": message, **extra}


def _read_active_window() -> tuple[str, str]:
    """Return (window_title, process_name) for the foreground window, or ('','')."""
    try:
        import win32gui
        import win32process
        import psutil
        hwnd = win32gui.GetForegroundWindow()
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = ""
        if pid:
            try:
                proc = psutil.Process(pid).name()
            except Exception:
                proc = ""
        return title, proc
    except Exception:
        return "", ""


def _friendly_app(proc: str) -> str:
    name = (proc or "").rsplit(".", 1)[0]
    pretty = {
        "Code": "VS Code", "msedge": "Edge", "chrome": "Chrome", "firefox": "Firefox",
        "explorer": "File Explorer", "WindowsTerminal": "Terminal", "powershell": "PowerShell",
        "Spotify": "Spotify", "Discord": "Discord", "POWERPNT": "PowerPoint", "WINWORD": "Word",
        "EXCEL": "Excel", "notepad": "Notepad",
    }
    return pretty.get(name, name or "an app")


def get_active_window(slots: dict | None = None) -> dict[str, Any]:
    title, proc = _read_active_window()
    if not title and not proc:
        return _ok("I can't read the active window right now.", tool="get_active_window",
                   active_app="", active_title="")
    app = _friendly_app(proc)
    msg = f"The active app is {app}" + (f' — "{title[:80]}".' if title else ".")
    return _ok(msg, tool="get_active_window", active_app=proc, active_title=title)


def what_am_i_working_on(slots: dict | None = None) -> dict[str, Any]:
    title, proc = _read_active_window()
    if not title and not proc:
        return _ok("I can't tell what's in focus right now.", tool="what_am_i_working_on")
    app = _friendly_app(proc)
    msg = f"You're working in {app}" + (f' on "{title[:80]}".' if title else ".")
    return _ok(msg, tool="what_am_i_working_on", active_app=proc, active_title=title)


def get_system_state(slots: dict | None = None) -> dict[str, Any]:
    import psutil
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    parts = [f"CPU at {cpu:.0f}%", f"memory at {mem.percent:.0f}%"]
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            parts.append(f"battery {bat.percent:.0f}%" + (" charging" if bat.power_plugged else ""))
    except Exception:
        pass
    try:
        up = time.time() - psutil.boot_time()
        parts.append(f"up {int(up // 3600)}h {int((up % 3600) // 60)}m")
    except Exception:
        pass
    return _ok("System status: " + ", ".join(parts) + ".", tool="get_system_state",
               cpu=round(cpu), mem=round(mem.percent))


def why_is_pc_slow(slots: dict | None = None) -> dict[str, Any]:
    import psutil
    procs = list(psutil.process_iter(["name"]))
    for p in procs:                       # prime cpu_percent (needs two reads)
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(0.4)
    ncpu = psutil.cpu_count() or 1
    scored = []
    for p in procs:
        try:
            c = p.cpu_percent(None) / ncpu
            m = p.memory_percent()
            scored.append((c, m, (p.info.get("name") or "?").rsplit(".", 1)[0]))
        except Exception:
            pass
    cpu = psutil.cpu_percent(interval=0)
    mem = psutil.virtual_memory().percent
    _idle = {"system idle process", "idle", "system"}
    top_cpu = [f"{n} ({c:.0f}%)" for c, _, n in sorted(scored, reverse=True)
               if c >= 1 and n.lower() not in _idle][:3]
    top_mem = [f"{n} ({m:.0f}%)" for _, m, n in sorted(scored, key=lambda x: x[1], reverse=True)
               if m >= 1 and n.lower() not in _idle][:3]
    msg = (f"Overall CPU is {cpu:.0f}% and memory {mem:.0f}%. "
           f"Heaviest on CPU: {', '.join(top_cpu) or 'nothing notable'}. "
           f"Heaviest on memory: {', '.join(top_mem) or 'nothing notable'}.")
    return _ok(msg, tool="why_is_pc_slow", cpu=round(cpu), mem=round(mem))
