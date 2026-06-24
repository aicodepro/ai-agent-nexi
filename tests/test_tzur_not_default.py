import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.clap_backend_manager import ClapBackendManager


def test_tzur_is_not_default():
    os.environ.pop("JARVIS_CLAP_BACKEND_ORDER", None)
    os.environ.pop("JARVIS_CLAP_PRIMARY", None)
    os.environ.pop("JARVIS_CLAP_FALLBACK", None)
    manager = ClapBackendManager(cooldown_ms=5000)
    assert manager._primary_name != "tzur"
    assert manager._fallback_name != "tzur"


def test_tzur_not_in_default_order():
    default_order = os.getenv("JARVIS_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn")
    assert "tzur" not in default_order


def test_dsp_clap_is_default_primary():
    os.environ.pop("JARVIS_CLAP_BACKEND_ORDER", None)
    os.environ.pop("JARVIS_CLAP_PRIMARY", None)
    manager = ClapBackendManager(cooldown_ms=5000)
    assert manager._primary_name == "dsp_clap"
