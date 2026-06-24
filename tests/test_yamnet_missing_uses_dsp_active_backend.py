import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.clap_backend_manager import ClapBackendManager


def test_yamnet_not_ready_uses_fallback():
    os.environ["NEXI_CLAP_BACKEND_ORDER"] = "yamnet,dsp_clap"
    os.environ["NEXI_CLAP_DEBUG"] = "false"
    manager = ClapBackendManager(cooldown_ms=5000)
    assert manager._primary_name == "yamnet"
    assert manager._primary_ready is False
    assert manager._fallback_name == "dsp_clap"
    assert manager._fallback_ready is True
    os.environ.pop("NEXI_CLAP_BACKEND_ORDER", None)
    os.environ.pop("NEXI_CLAP_DEBUG", None)


def test_yamnet_missing_does_not_crash():
    os.environ["NEXI_CLAP_BACKEND_ORDER"] = "yamnet,dsp_clap"
    os.environ["NEXI_CLAP_DEBUG"] = "false"
    try:
        manager = ClapBackendManager(cooldown_ms=5000)
        status = manager.get_status()
        assert "active_backend" not in status  # get_status doesn't have active_backend
        assert status["primary"] == "yamnet"
        assert status["primary_ready"] is False
    finally:
        os.environ.pop("NEXI_CLAP_BACKEND_ORDER", None)
        os.environ.pop("NEXI_CLAP_DEBUG", None)


def test_dsp_works_when_primary_yamnet_gone():
    os.environ["NEXI_CLAP_BACKEND_ORDER"] = "yamnet,dsp_clap"
    os.environ["NEXI_CLAP_DEBUG"] = "false"
    try:
        manager = ClapBackendManager(cooldown_ms=5000)
        assert manager._fallback_ready is True
        result = manager._try_backend(manager._fallback, "dsp_clap", b"\x00\x01" * 320)
        assert result is not None
    finally:
        os.environ.pop("NEXI_CLAP_BACKEND_ORDER", None)
        os.environ.pop("NEXI_CLAP_DEBUG", None)
