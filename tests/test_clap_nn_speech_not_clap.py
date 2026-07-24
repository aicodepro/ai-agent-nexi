from __future__ import annotations

from engine.clap_nn_backend import ClapNNBackend


def test_speech_pattern_not_misclassified_as_clap():
    """Without a trained model, speech-like audio must not trigger clap."""
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    # Simulate speech-like audio: continuous low-to-medium amplitude
    import struct
    samples = []
    for i in range(16000):
        val = int(8000 * (i % 100) / 100)
        samples.append(max(-32768, min(32767, val)))
    frame = struct.pack(f"<{len(samples)}h", *samples)
    result = backend.process_pcm16(frame, 0.0)
    assert not result.is_clap, "Speech-like audio should not be clap without model"


def test_speech_edge_case_not_clap():
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    frame = b"\x00" * 32000  # 1 second of silence
    result = backend.process_pcm16(frame, 0.0)
    assert not result.is_clap
