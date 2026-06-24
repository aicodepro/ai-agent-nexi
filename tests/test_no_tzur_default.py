from __future__ import annotations

import os


def test_tzur_not_in_default_backend_order():
    """Tzur must not be in the default NEXI_CLAP_BACKEND_ORDER."""
    order = os.getenv("NEXI_CLAP_BACKEND_ORDER", "clap_nn").strip().lower()
    assert "tzur" not in order, f"Tzur should not be in default backend order: {order}"


def test_nexi_not_in_default_backend_order():
    """Nexi clap must not be in the default backend order."""
    order = os.getenv("NEXI_CLAP_BACKEND_ORDER", "clap_nn").strip().lower()
    assert "nexi" not in order, f"Nexi clap should not be in default order: {order}"


def test_clap_backend_manager_does_not_default_to_tzur():
    from engine.clap_backend_manager import ClapBackendManager
    mgr = ClapBackendManager()
    assert mgr.primary_name != "tzur", "Tzur must not be the default primary"
