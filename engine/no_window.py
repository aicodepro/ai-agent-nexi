"""Zero terminal windows: suppress console/PowerShell windows on subprocess spawns.

Mirrors Mark-48's "zero terminal windows" — on Windows, inject CREATE_NO_WINDOW into
every subprocess.Popen so no cmd/PowerShell window flashes during operations. Installed
once from the app entry points (NOT at import, so the test suite is unaffected).
Opt out with NEXI_SHOW_TERMINALS=1.

ponytail: covers subprocess.* (run/call/Popen all route through Popen). os.system('start …')
is left alone — it launches GUI apps and leaves no lingering console. If a bare os.system
console ever flashes, convert that specific call to subprocess.run.
"""
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000  # winbase.h / subprocess.CREATE_NO_WINDOW

_installed = False


def _enabled():
    if sys.platform != "win32":
        return False
    return os.environ.get("NEXI_SHOW_TERMINALS", "").strip().lower() not in ("1", "true", "yes")


def _inject(kwargs):
    """Return kwargs with CREATE_NO_WINDOW added, unless disabled or caller set flags."""
    if _enabled() and not kwargs.get("creationflags"):
        kwargs = {**kwargs, "creationflags": CREATE_NO_WINDOW}
    return kwargs


def install():
    """Idempotently wrap subprocess.Popen to hide console windows on Windows."""
    global _installed
    if _installed or not _enabled():
        return
    _orig_init = subprocess.Popen.__init__

    def _patched_init(self, *args, **kwargs):
        return _orig_init(self, *args, **_inject(kwargs))

    _patched_init._nexi_orig = _orig_init  # allow uninstall/inspection
    subprocess.Popen.__init__ = _patched_init
    _installed = True
