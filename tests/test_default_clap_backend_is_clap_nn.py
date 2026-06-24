from __future__ import annotations

import os


def test_default_clap_primary_is_dsp_clap():
    """JARVIS_CLAP_PRIMARY defaults to dsp_clap (no-training backend)."""
    from engine.clap_backend_manager import ClapBackendManager
    mgr = ClapBackendManager(cooldown_ms=5000)
    assert mgr.primary_name == "dsp_clap", f"Expected dsp_clap, got {mgr.primary_name}"


def test_default_clap_backend_order_is_dsp_clap():
    """JARVIS_CLAP_BACKEND_ORDER defaults to dsp_clap,clap_nn."""
    from engine.clap_backend_manager import ClapBackendManager
    mgr = ClapBackendManager(cooldown_ms=5000)
    assert mgr.primary_name == "dsp_clap"
    assert mgr.fallback_name == "clap_nn"


def test_clap_backend_manager_can_still_use_clap_nn_with_env(monkeypatch):
    """Setting JARVIS_CLAP_BACKEND_ORDER to clap_nn still works."""
    monkeypatch.setenv("JARVIS_CLAP_BACKEND_ORDER", "clap_nn")
    from engine.clap_backend_manager import ClapBackendManager
    mgr = ClapBackendManager(cooldown_ms=5000)
    assert mgr.primary_name == "clap_nn"
