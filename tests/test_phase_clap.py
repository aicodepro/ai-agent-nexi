import numpy as np
import pytest
from wake.clap import ClapDetector


def _frame(arr) -> bytes:
    return (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def clap_frame(seed: int = 0, n: int = 1280, burst: int = 200, amp: float = 0.5) -> bytes:
    rng = np.random.default_rng(seed)
    x = np.zeros(n, dtype=np.float32)
    x[100:100 + burst] = rng.normal(0.0, amp, burst)
    return _frame(x)


def tone_frame(n: int = 1280, freq: int = 440, amp: float = 0.5) -> bytes:
    t = np.arange(n)
    return _frame(amp * np.sin(2 * np.pi * freq * t / 16000))


def test_single_clap_detected():
    d = ClapDetector()
    assert d._is_single_clap(clap_frame()) is True


def test_sustained_tone_rejected():
    # A loud continuous tone (voice/music/hum) is not impulsive -> rejected.
    d = ClapDetector()
    assert d._is_single_clap(tone_frame()) is False


def test_silence_rejected():
    d = ClapDetector()
    assert d._is_single_clap(_frame(np.zeros(1280, dtype=np.float32))) is False


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


def test_double_clap_triggers(monkeypatch):
    import wake.clap as clapmod
    clk = _Clock(100000.0)
    monkeypatch.setattr(clapmod.time, "time", clk.time)

    d = ClapDetector()
    r1 = d.process_frame(clap_frame(seed=1))
    assert r1["detected"] is False
    assert r1["reason"] == "first_clap"

    clk.t = 100000.0 + 0.4  # 400 ms gap, within [min_gap, max_gap]
    r2 = d.process_frame(clap_frame(seed=2))
    assert r2["detected"] is True
    assert "double_clap" in r2["reason"]


def test_double_clap_too_fast_rejected(monkeypatch):
    import wake.clap as clapmod
    clk = _Clock(200000.0)
    monkeypatch.setattr(clapmod.time, "time", clk.time)

    d = ClapDetector()
    d.process_frame(clap_frame(seed=1))
    clk.t = 200000.0 + 0.05  # 50 ms — too fast for a deliberate double clap
    r = d.process_frame(clap_frame(seed=2))
    assert r["detected"] is False
