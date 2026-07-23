"""Streaming/edge-trigger logic for ClapNNBackend.

The pipeline feeds 80 ms frames but the CNN classifies a ~600 ms window. The backend
keeps a rolling buffer and only invokes the CNN on a clap-like onset, then suppresses
re-fires for a refractory period so ONE physical clap = ONE event (the double-clap state
machine turns two events into a wake). These tests mock the CNN so the streaming logic is
verified deterministically, without a model.
"""
import struct

from engine.clap_nn_backend import ClapNNBackend

SR = 16000
FRAME = 1280  # 80 ms @ 16 kHz, matches NEXI_WAKE_FRAME_MS


def _frame(peak_val: int) -> bytes:
    if peak_val <= 0:
        return struct.pack(f"<{FRAME}h", *([0] * FRAME))
    return struct.pack(f"<{FRAME}h", *([0] * (FRAME - 50) + [peak_val] * 50))


def _ready_backend(prob: float, calls: list | None = None) -> ClapNNBackend:
    b = ClapNNBackend(model_path="/nonexistent/model.pth")  # starts not-ready
    b._loaded = True
    b._ready = True
    b._model = object()

    def fake_classify() -> float:
        if calls is not None:
            calls.append(1)
        return prob

    b._classify_window = fake_classify  # type: ignore[method-assign]
    b._trigger_peak = 0.12
    b._refractory_sec = 0.12
    b._threshold = 0.85
    return b


def test_onset_gate_skips_quiet_frames():
    calls: list = []
    b = _ready_backend(0.99, calls)
    fires = sum(b.process_pcm16(_frame(0), i * 0.08).is_clap for i in range(10))
    assert fires == 0
    assert calls == []  # CNN is never invoked on sub-trigger frames


def test_single_clap_fires_one_edge_event():
    b = _ready_backend(0.99)
    # one clap spanning two loud frames; must fire exactly once (refractory suppresses the 2nd)
    seq = [0, 0, 1, 1, 0, 0]
    events = [i for i, loud in enumerate(seq)
              if b.process_pcm16(_frame(30000 if loud else 0), i * 0.08).is_clap]
    assert events == [2], f"one clap should fire once, got {events}"


def test_refractory_then_refire():
    b = _ready_backend(0.99)
    events = [t for t in (0.0, 0.08, 0.30)
              if b.process_pcm16(_frame(30000), t).is_clap]
    assert events == [0.0, 0.30]  # 0.08 is inside the 120 ms refractory


def test_cnn_rejects_below_threshold():
    b = _ready_backend(0.10)  # loud onset, but CNN says not-clap
    r = b.process_pcm16(_frame(30000), 0.0)
    assert not r.is_clap
    assert r.reason == "onset_not_clap"


def test_double_clap_yields_two_events():
    b = _ready_backend(0.99)
    # two claps 300 ms apart (typical double-clap) -> two separate events for the state machine
    events = [t for t in (0.0, 0.30) if b.process_pcm16(_frame(30000), t).is_clap]
    assert events == [0.0, 0.30]
