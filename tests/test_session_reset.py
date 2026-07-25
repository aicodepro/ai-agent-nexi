"""Session-reset aggregator (engine/session_reset.py)."""
import sys
import types

import engine.session_reset as sr


def test_runs_all_and_skips_failures(monkeypatch):
    calls = []
    good = types.ModuleType("nexi_fake_good")
    good.reset = lambda: calls.append("g")
    bad = types.ModuleType("nexi_fake_bad")

    def boom():
        raise RuntimeError("x")

    bad.reset = boom
    monkeypatch.setitem(sys.modules, "nexi_fake_good", good)
    monkeypatch.setitem(sys.modules, "nexi_fake_bad", bad)
    monkeypatch.setattr(sr, "_RESETS", [
        ("nexi_fake_good", "reset"),
        ("nexi_fake_bad", "reset"),   # raises -> skipped, does not block
        ("nexi_fake_good", "reset"),
    ])
    done = sr.reset_session()
    assert calls == ["g", "g"]
    assert done == ["nexi_fake_good.reset", "nexi_fake_good.reset"]


def test_missing_module_is_skipped(monkeypatch):
    monkeypatch.setattr(sr, "_RESETS", [("engine.does_not_exist", "nope")])
    assert sr.reset_session() == []
