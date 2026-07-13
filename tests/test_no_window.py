"""Zero-terminal-windows suppression logic (engine/no_window.py)."""
import engine.no_window as nw


def test_injects_flag_on_windows(monkeypatch):
    monkeypatch.setattr(nw.sys, "platform", "win32")
    monkeypatch.delenv("NEXI_SHOW_TERMINALS", raising=False)
    out = nw._inject({"shell": True})
    assert out["creationflags"] == nw.CREATE_NO_WINDOW
    assert out["shell"] is True


def test_disabled_by_env(monkeypatch):
    monkeypatch.setattr(nw.sys, "platform", "win32")
    monkeypatch.setenv("NEXI_SHOW_TERMINALS", "1")
    assert "creationflags" not in nw._inject({"shell": True})


def test_noop_off_windows(monkeypatch):
    monkeypatch.setattr(nw.sys, "platform", "linux")
    assert "creationflags" not in nw._inject({})


def test_respects_caller_flags(monkeypatch):
    monkeypatch.setattr(nw.sys, "platform", "win32")
    monkeypatch.delenv("NEXI_SHOW_TERMINALS", raising=False)
    out = nw._inject({"creationflags": 0x10})  # CREATE_NEW_CONSOLE — leave it
    assert out["creationflags"] == 0x10
