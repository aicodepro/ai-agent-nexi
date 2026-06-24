from __future__ import annotations

import os


def test_clap_nn_backend_module_exists():
    """The clap_nn_backend module must be importable."""
    try:
        from engine import clap_nn_backend
        assert hasattr(clap_nn_backend, "ClapNNBackend")
    except ImportError as e:
        raise AssertionError(f"clap_nn_backend import failed: {e}")


def test_clap_nn_backend_class_has_required_methods():
    from engine.clap_nn_backend import ClapNNBackend
    assert hasattr(ClapNNBackend, "process_pcm16")
    assert hasattr(ClapNNBackend, "get_status")
    assert hasattr(ClapNNBackend, "reset")


def test_clap_nn_backend_init_without_model():
    """Backend should init even without model (ready=False)."""
    from engine.clap_nn_backend import ClapNNBackend
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    status = backend.get_status()
    assert not status["ready"]
    assert "not found" in status["last_error"].lower()
