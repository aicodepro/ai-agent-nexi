import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.clap_backend_manager import ClapBackendManager


def _make_clap_event(backend):
    return {"clap": True, "wake": False, "source": None,
            "backend": backend, "backend_used": backend,
            "fallback_used": False, "cooldown": False,
            "amplitude": 0.5, "threshold": 0.0,
            "reason": "clap_detected", "pattern": []}


class FakeDsp:
    def process_pcm16(self, frame, ts):
        return _make_clap_event("dsp_clap")
    def get_debug_snapshot(self):
        return {}
    def reset(self):
        pass


def test_single_clap_no_wake():
    fake = FakeDsp()
    manager = ClapBackendManager(clock=time.time, cooldown_ms=5000)
    manager._primary = fake
    manager._primary_name = "dsp_clap"
    manager._primary_ready = True
    manager._debug = False

    now = time.time()
    event = _make_clap_event("dsp_clap")
    result = manager._apply_double_clap_state(event, now)
    assert result["wake"] is False
    assert result.get("source") is None


def test_single_clap_sets_waiting():
    fake = FakeDsp()
    manager = ClapBackendManager(clock=time.time, cooldown_ms=5000)
    manager._primary = fake
    manager._primary_name = "dsp_clap"
    manager._primary_ready = True
    manager._debug = False

    now = time.time()
    event = _make_clap_event("dsp_clap")
    manager._apply_double_clap_state(event, now)
    state = manager._double_clap.get_status()["state"]
    assert state in ("stage_first_clap", "first_clap_waiting"), f"Expected waiting state, got {state}"
