from __future__ import annotations

import time


def _clap_event() -> dict:
    return {
        "clap": True,
        "wake": False,
        "source": None,
        "backend": "dsp_clap",
        "backend_used": "dsp_clap",
        "fallback_used": False,
        "cooldown": False,
        "amplitude": 0.5,
        "reason": "clap_detected",
    }


def test_double_clap_accepts_3000ms_gap_by_default(monkeypatch):
    monkeypatch.delenv("NEXI_CLAP_MAX_GAP_MS", raising=False)
    monkeypatch.delenv("CLAP_MAX_GAP_MS", raising=False)

    from engine.clap_backend_manager import ClapBackendManager

    manager = ClapBackendManager(clock=time.time, cooldown_ms=1500)
    now = time.time()
    assert manager._apply_double_clap_state(_clap_event(), now)["wake"] is False
    second = manager._apply_double_clap_state(_clap_event(), now + 3.0)

    assert second["wake"] is True
    assert second["source"] == "double_clap"
    assert 2990 <= second["gap_ms"] <= 3010
