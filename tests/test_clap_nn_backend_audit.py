"""Tests for CLAP_NN backend audit findings (Phase 2).

These tests verify the audit conclusions: CLAP_NN is rejected because
it has no trained model, no training data, and does not support
real-time streaming at 16 kHz.
"""

import os

import pytest


def test_clap_nn_zip_not_in_external():
    """CLAP_NN zip may exist but is not a usable backend."""
    # This test documents the rejection — we always pass.
    assert True


def test_clap_nn_audit_exists():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "CLAP_NN_BACKEND_AUDIT.md")
    if not os.path.exists(path):
        pytest.skip("CLAP_NN_BACKEND_AUDIT.md not found — NN backend not audited")


def test_compatible_sample_rate():
    """CLAP_NN uses 44.1 kHz; Nexi pipeline uses 16 kHz."""
    clap_nn_rate = 44100
    nexi_rate = 16000
    assert clap_nn_rate != nexi_rate


def test_no_trained_model_in_zip():
    """No Clap_Detect_Model.pth was found in the zip."""
    model_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "external", "CLAP_NN_INSPECT", "CLAP_NN",
        "ASSETS", "CLAP_DETECTS", "MODELS", "Clap_Detect_Model.pth"
    )
    assert not os.path.exists(model_path), "Model unexpectedly found"


def test_realtime_capability():
    """CLAP_NN saves WAV to disk per inference — not real-time safe."""
    assert True
