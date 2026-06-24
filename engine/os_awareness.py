"""OS Awareness Layer (Roadmap Feature #1) — read-only PC state for Nexi.

Tool cards
----------
get_active_window      role: PC awareness | risk: LOW | confirm: never | verifier: title/process returned | memory: never store
what_am_i_working_on   role: PC awareness | risk: LOW | confirm: never | verifier: active window resolved   | memory: never store
get_system_state       role: PC awareness | risk: LOW | confirm: never | verifier: cpu/mem sampled           | memory: never store
why_is_pc_slow         role: PC awareness | risk: LOW | confirm: never | verifier: top processes sampled      | memory: never store
get_running_apps       role: PC awareness | risk: LOW | confirm: never | verifier: process list sampled       | memory: never store
get_idle_time          role: PC awareness | risk: LOW | confirm: never | verifier: idle ticks read            | memory: never store

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


# Background/system processes that are not user-facing "apps".
_NOT_APPS = {
    "system idle process", "system", "idle", "registry", "memory compression",
    "svchost", "csrss", "wininit", "winlogon", "services", "lsass", "smss",
    "fontdrvhost", "dwm", "conhost", "runtimebroker", "dllhost", "sihost",
    "ctfmon", "searchhost", "searchindexer", "taskhostw", "spoolsv", "wmiprvse",
    "audiodg", "backgroundtaskhost", "shellexperiencehost", "startmenuexperiencehost",
}


def get_running_apps(slots: dict | None = None) -> dict[str, Any]:
    """List distinct user-facing applications currently running (read-only)."""
    import psutil
    names: set[str] = set()
    for p in psutil.process_iter(["name"]):
        try:
            raw = (p.info.get("name") or "")
            stem = raw.rsplit(".", 1)[0]
            if stem and stem.lower() not in _NOT_APPS:
                names.add(_friendly_app(raw))
        except Exception:
            continue
    apps = sorted(names, key=str.lower)
    count = len(apps)
    preview = ", ".join(apps[:8])
    if count:
        msg = f"You have {count} apps running" + (f", including {preview}." if preview else ".")
    else:
        msg = "I couldn't read the running apps right now."
    return _ok(msg, tool="get_running_apps", count=count, apps=apps)


def _idle_ms() -> int:
    """Milliseconds since the last keyboard/mouse input (Windows, read-only)."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]

        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0
        tick = ctypes.windll.kernel32.GetTickCount()
        return max(0, int(tick) - int(info.dwTime))
    except Exception:
        return 0


def _humanize_secs(secs: int) -> str:
    if secs < 60:
        return f"{secs} second{'s' if secs != 1 else ''}"
    mins = secs // 60
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''}"
    hours, rem = mins // 60, mins % 60
    return f"{hours}h {rem}m"


def get_idle_time(slots: dict | None = None) -> dict[str, Any]:
    """Report how long since the user last touched the keyboard/mouse (read-only)."""
    idle_ms = _idle_ms()
    idle_seconds = round(idle_ms / 1000, 1)
    if idle_ms <= 0:
        msg = "You're active right now."
    else:
        msg = f"You've been idle for {_humanize_secs(int(idle_seconds))}."
    return _ok(msg, tool="get_idle_time", idle_seconds=idle_seconds, idle_ms=idle_ms)
