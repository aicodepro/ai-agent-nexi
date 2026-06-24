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


def test_gap_1839_accepts():
    saved = {k: os.environ.pop(k, None) for k in ["NEXI_CLAP_MAX_GAP_MS", "CLAP_MAX_GAP_MS", "NEXI_CLAP_MIN_GAP_MS", "CLAP_MIN_GAP_MS"]}
    try:
        manager = ClapBackendManager(clock=time.time, cooldown_ms=5000)
        manager._max_gap_ms = 2200.0
        manager._min_gap_ms = 120.0
        manager._primary = FakeDsp()
        manager._primary_name = "dsp_clap"
        manager._primary_ready = True
        manager._debug = False

        now = time.time()
        r1 = manager._apply_double_clap_state(_make_clap_event("dsp_clap"), now)
        later = now + 1.839
        r2 = manager._apply_double_clap_state(_make_clap_event("dsp_clap"), later)
        assert r2["wake"] is True
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
