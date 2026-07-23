"""The wake model must not fire on non-wake audio.

Regression: models/hey_nexi.onnx was replaced with an incompatible 5.2MB ONNX
(the working one is ~857KB). It scored 1.0 on EVERYTHING — pure silence
included — so the only thing standing between ambient noise and a wake was the
RMS noise gate. Ordinary speech ("nice to meet you") woke Nexi constantly.

A degenerate wake model is silent in every other test: process_frame() still
"works", the pipeline still runs, only real-world behaviour is ruined. So assert
the model's actual scores on audio that is definitively NOT the wake word.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

pytest.importorskip("openwakeword", reason="openwakeword only present in the project .venv")
np = pytest.importorskip("numpy")

FRAME = 1280  # 80ms @ 16kHz — the live pipeline's frame size


def _model_path() -> str:
    configured = (os.getenv("OPENWAKEWORD_MODEL_PATH") or "models/hey_nexi.onnx").strip()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = configured if os.path.isabs(configured) else os.path.join(root, configured)
    if not os.path.exists(path):
        pytest.skip(f"wake model not present at {path}")
    return path


@pytest.fixture(scope="module")
def scorer():
    from engine.openwakeword_scorer import OpenWakeWordScorer

    s = OpenWakeWordScorer(model_path=_model_path())
    if getattr(s, "model_name", "unloaded") == "unloaded":
        pytest.skip("wake model failed to load")
    return s


def _threshold() -> float:
    try:
        return float(os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


@pytest.mark.parametrize("label,build", [
    ("silence", lambda rng: np.zeros(FRAME, dtype=np.int16)),
    ("quiet_noise", lambda rng: rng.normal(0, 30, FRAME).astype(np.int16)),
    ("loud_white_noise", lambda rng: rng.normal(0, 6000, FRAME).astype(np.int16)),
    ("tone_440hz", lambda rng: (3000 * np.sin(2 * np.pi * 440 * np.arange(FRAME) / 16000)).astype(np.int16)),
])
def test_wake_model_does_not_fire_on_non_wake_audio(scorer, label, build):
    rng = np.random.default_rng(0)
    frame = build(rng).tobytes()
    scores = [float(scorer.score(frame)) for _ in range(6)]
    worst = max(scores)
    assert worst < _threshold(), (
        f"wake model scored {worst:.4f} on {label!r} (threshold {_threshold()}). "
        f"A degenerate/wrong model fires on everything — check models/hey_nexi.onnx "
        f"(the working model is ~857KB and scores ~0.004 here)."
    )


def test_wake_model_is_not_saturated(scorer):
    """A model that returns ~1.0 for every input is broken, whatever the threshold."""
    rng = np.random.default_rng(1)
    frames = [
        np.zeros(FRAME, dtype=np.int16),
        rng.normal(0, 100, FRAME).astype(np.int16),
        rng.normal(0, 8000, FRAME).astype(np.int16),
    ]
    scores = [float(scorer.score(f.tobytes())) for f in frames for _ in range(3)]
    assert max(scores) < 0.9, f"wake model is saturated at {max(scores):.4f} — it fires on any audio: {scores}"


def test_wake_model_actually_detects_the_wake_word():
    """The other half of the contract: a model that never false-fires but also never
    WAKES is equally useless. Streams the real hey_nexi recordings through the scorer
    the way the live pipeline does (fresh state per clip — it is a streaming model).
    """
    import glob
    import wave

    from engine.openwakeword_scorer import OpenWakeWordScorer

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    files = sorted(glob.glob(os.path.join(root, "data", "wake", "hey_nexi", "*.wav")))[:12]
    if not files:
        pytest.skip("no data/wake/hey_nexi recordings present")

    def _peak(path: str) -> float:
        with wave.open(path, "rb") as w:
            channels = w.getnchannels()
            raw = w.readframes(w.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)[:, 0]
        s = OpenWakeWordScorer(model_path=_model_path())
        best = 0.0
        for i in range(0, len(audio) - FRAME, FRAME):
            best = max(best, float(s.score(audio[i:i + FRAME].tobytes())))
        return best

    peaks = [_peak(f) for f in files]
    detected = sum(1 for p in peaks if p >= _threshold())
    # Recall, not perfection: some captures are near-silent. The broken 5.2MB model
    # scored 1.0 on everything, so this only passes for a model with real separation.
    assert detected >= len(files) // 2, (
        f"wake model only detected {detected}/{len(files)} real 'hey nexi' recordings "
        f"(peaks={[round(p, 3) for p in peaks]}). It does not wake — check models/hey_nexi.onnx."
    )
