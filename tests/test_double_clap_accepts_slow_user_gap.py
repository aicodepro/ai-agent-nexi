import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.clap_backend_manager import ClapBackendManager


def _make_clap_event(backend, gap_ms=None):
    return {"clap": True, "wake": False, "source": None,
            "backend": backend, "backend_used": backend,
            "fallback_used": False, "cooldown": False,
            "amplitude": 0.5, "threshold": 0.0, "gap_ms": gap_ms,
            "reason": "clap_detected", "pattern": []}


class FakeDspClap:
    def process_pcm16(self, frame, ts):
        return _make_clap_event("dsp_clap")
    def get_debug_snapshot(self):
        return {}
    def reset(self):
        pass


def _make_manager():
    saved = {}
    for k in ["JARVIS_CLAP_MAX_GAP_MS", "CLAP_MAX_GAP_MS", "JARVIS_CLAP_MIN_GAP_MS", "CLAP_MIN_GAP_MS"]:
        saved[k] = os.environ.pop(k, None)
    manager = ClapBackendManager(clock=time.time, cooldown_ms=5000)
    manager._max_gap_ms = 2200.0
    manager._min_gap_ms = 120.0
    manager._debug = False
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
    return manager


def test_double_clap_accepts_1800ms_gap():
    manager = _make_manager()
    manager._primary = FakeDspClap()
    manager._primary_name = "dsp_clap"
    manager._primary_ready = True

    now = time.time()
    first = _make_clap_event("dsp_clap")
    r1 = manager._apply_double_clap_state(first, now)
    assert r1["wake"] is False
    state = manager._double_clap.get_status()["state"]
    assert state in ("stage_first_clap", "first_clap_waiting"), f"Expected waiting state, got {state}"

    later = now + 1.8
    second = _make_clap_event("dsp_clap")
    r2 = manager._apply_double_clap_state(second, later)
    assert r2["wake"] is True
    assert r2["source"] == "double_clap"


def test_double_clap_accepts_2000ms_gap():
    manager = _make_manager()
    manager._primary = FakeDspClap()
    manager._primary_name = "dsp_clap"
    manager._primary_ready = True

    now = time.time()
    first = _make_clap_event("dsp_clap")
    r1 = manager._apply_double_clap_state(first, now)
    later = now + 2.0
    second = _make_clap_event("dsp_clap")
    r2 = manager._apply_double_clap_state(second, later)
    assert r2["wake"] is True


def test_double_clap_rejects_2500ms_gap():
    manager = _make_manager()
    manager._primary = FakeDspClap()
    manager._primary_name = "dsp_clap"
    manager._primary_ready = True

    now = time.time()
    first = _make_clap_event("dsp_clap")
    r1 = manager._apply_double_clap_state(first, now)
    later = now + 2.5
    second = _make_clap_event("dsp_clap")
    r2 = manager._apply_double_clap_state(second, later)
    assert r2["wake"] is False
