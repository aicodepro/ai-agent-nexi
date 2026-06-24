import os
import sys
import socket
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import _is_port_available, _find_free_port, _env_int


def test_env_override_port():
    custom_port = 8999
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", custom_port))
        busy_port = s.getsockname()[1]
        s.listen(1)
        os.environ["NEXI_UI_PORT"] = str(busy_port)
        os.environ["NEXI_UI_AUTO_PORT"] = "false"
        try:
            from main import _find_free_port
            result, reason = _find_free_port("localhost", busy_port, max_port=8020)
            assert result == busy_port
        finally:
            os.environ.pop("NEXI_UI_PORT", None)
            os.environ.pop("NEXI_UI_AUTO_PORT", None)


def test_env_auto_port_disabled_does_not_fallback():
    os.environ["NEXI_UI_AUTO_PORT"] = "false"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            busy_port = s.getsockname()[1]
            s.listen(1)
            result, reason = _find_free_port("localhost", busy_port)
            assert result == busy_port
    finally:
        os.environ.pop("NEXI_UI_AUTO_PORT", None)


def test_env_auto_port_default_is_true():
    from main import _env_bool
    assert _env_bool("NEXI_UI_AUTO_PORT", True) is True
