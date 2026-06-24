import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeKeyboard:
    def __init__(self, fail_primary=False):
        self.fail_primary = fail_primary
        self.callbacks = []
        self.hotkeys = []

    def add_hotkey(self, hotkey, callback):
        if self.fail_primary and hotkey == "windows+j":
            raise RuntimeError("blocked")
        self.hotkeys.append(hotkey)
        self.callbacks.append(callback)
        return len(self.hotkeys)

    def remove_hotkey(self, handle):
        return None


def test_hotkey_uses_internal_wake(monkeypatch):
    fake = FakeKeyboard()
    calls = []
    monkeypatch.setenv("JARVIS_HOTKEY_ENABLED", "true")
    monkeypatch.setenv("JARVIS_HOTKEY", "win+j")
    monkeypatch.setitem(sys.modules, "keyboard", fake)

    from engine.hotkey_wake import start_hotkey_listener, stop_hotkey_listener

    listener = start_hotkey_listener(callback=lambda source: calls.append(source))
    assert listener is not None
    assert "windows+j" in fake.hotkeys
    fake.callbacks[0]()
    assert calls == ["hotkey"]
    stop_hotkey_listener(listener)


def test_win_j_fallback_registered_when_primary_unavailable(monkeypatch, capsys):
    fake = FakeKeyboard(fail_primary=True)
    monkeypatch.setenv("JARVIS_HOTKEY_ENABLED", "true")
    monkeypatch.setenv("JARVIS_HOTKEY", "win+j")
    monkeypatch.setenv("JARVIS_HOTKEY_FALLBACK", "ctrl+alt+j")
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    monkeypatch.setitem(sys.modules, "pynput", SimpleNamespace())

    from engine.hotkey_wake import start_hotkey_listener, stop_hotkey_listener

    listener = start_hotkey_listener(callback=lambda source: True)
    out = capsys.readouterr().out
    assert "[HOTKEY] win+j unavailable" in out
    assert "[HOTKEY] fallback registered hotkey=ctrl+alt+j" in out
    assert "ctrl+alt+j" in fake.hotkeys
    stop_hotkey_listener(listener)
