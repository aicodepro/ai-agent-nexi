"""Vision acknowledgement + cooldown (engine/app/phase3_command_bridge.py)."""
import time

import engine.app.phase3_command_bridge as m

B = m.Phase3CommandBridge


def test_cooldown_off_by_default(monkeypatch):
    monkeypatch.delenv("NEXI_VISION_COOLDOWN_MS", raising=False)
    assert B._vision_cooldown_s() == 0.0  # opt-in; disabled unless env set


def test_cooldown_disabled_never_trips(monkeypatch):
    monkeypatch.delenv("NEXI_VISION_COOLDOWN_MS", raising=False)
    B._mark_vision_capture()
    assert B._vision_on_cooldown() is False  # off -> never short-circuits


def test_cooldown_from_env(monkeypatch):
    monkeypatch.setenv("NEXI_VISION_COOLDOWN_MS", "1500")
    assert B._vision_cooldown_s() == 1.5


def test_capture_then_on_cooldown(monkeypatch):
    monkeypatch.setenv("NEXI_VISION_COOLDOWN_MS", "4000")
    B._mark_vision_capture()
    assert B._vision_on_cooldown() is True


def test_cooldown_expires(monkeypatch):
    monkeypatch.setenv("NEXI_VISION_COOLDOWN_MS", "4000")
    B._mark_vision_capture()
    B._last_vision_ts -= 10  # pretend 10s elapsed
    assert B._vision_on_cooldown() is False


def test_ack_is_non_blocking(monkeypatch):
    import sys
    import types
    stub = types.ModuleType("engine.command")
    stub.speak = lambda *a, **k: None  # thread picks this up; no real TTS
    monkeypatch.setitem(sys.modules, "engine.command", stub)
    t0 = time.monotonic()
    B._vision_ack()  # spawns daemon thread; must return immediately
    time.sleep(0.05)  # let the daemon run against the stub
    assert (time.monotonic() - t0) < 0.5
