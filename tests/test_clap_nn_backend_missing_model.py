from __future__ import annotations

from engine.clap_nn_backend import ClapNNBackend


def test_clap_nn_missing_model_returns_no_clap():
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    result = backend.process_pcm16(b"\x00" * 3200, 0.0)
    assert not result.is_clap
    assert "not found" in result.reason.lower() or "model" in result.reason.lower()


def test_clap_nn_missing_model_has_clear_error():
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    status = backend.get_status()
    assert not status["ready"]
    assert not status["loaded"]


def test_clap_nn_missing_model_does_not_crash():
    """Processing any PCM16 with missing model must not raise."""
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    try:
        result = backend.process_pcm16(b"\x00\x01\x02\x03" * 1600, 1.0)
        assert not result.is_clap
    except Exception as e:
        raise AssertionError(f"process_pcm16 raised {type(e).__name__}: {e}")
