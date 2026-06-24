import math
import os
import struct
import sys
import time as time_module

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def make_clap_signal(total=1280):
    samples = [0] * total
    start = total * 3 // 4
    for i in range(200):
        idx = start + i
        if idx >= total:
            break
        val = (math.sin(2 * math.pi * 3500 * i / 16000.0) * 0.4 + math.sin(2 * math.pi * 5000 * i / 16000.0) * 0.4) * (1.0 - i / 200) * 0.6
        samples[idx] = int(val * 32767)
    return struct.pack(f"<{len(samples)}h", *samples)


class Clock:
    def __init__(self):
        self.t = 1000.0
    def __call__(self):
        return self.t
    def advance(self, sec):
        self.t += sec


def test_double_clap_gap_window(monkeypatch):
    monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "dsp_clap")
    monkeypatch.setenv("NEXI_CLAP_MIN_GAP_MS", "160")
    monkeypatch.setenv("NEXI_CLAP_MAX_GAP_MS", "950")
    clock = Clock()
    monkeypatch.setattr(time_module, "time", clock)
    from engine.clap_backend_manager import ClapBackendManager
    mgr = ClapBackendManager(clock=clock, cooldown_ms=1800)
    for gap in (0.17, 0.4, 0.9):
        mgr.reset()
        clock.advance(10.0)
        r1 = mgr.process_audio_chunk(make_clap_signal())
        clock.advance(gap)
        r2 = mgr.process_audio_chunk(make_clap_signal())
        assert r1["clap"] is True and r1["wake"] is False
        assert r2["wake"] is True
