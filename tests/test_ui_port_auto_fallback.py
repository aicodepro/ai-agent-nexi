import os
import sys
import socket
import threading
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import _is_port_available, _find_free_port, _env_bool, _env_int


def test_port_available_returns_true_for_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        port = s.getsockname()[1]
        s.close()
        time.sleep(0.05)
        assert _is_port_available("localhost", port) is True


def test_port_available_returns_false_for_bound_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        port = s.getsockname()[1]
        s.listen(1)
        assert _is_port_available("localhost", port) is False


def test_find_free_port_returns_preferred():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        port = s.getsockname()[1]
        s.close()
        time.sleep(0.05)
        selected, reason = _find_free_port("localhost", port, max_port=port + 5)
        assert selected == port
        assert reason == ""


def test_find_free_port_falls_back_on_conflict():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        busy_port = s.getsockname()[1]
        s.listen(1)
        selected, reason = _find_free_port("localhost", busy_port, max_port=busy_port + 5)
        assert selected != busy_port, f"selected={selected} should differ from busy_port={busy_port}"
        assert "in_use" in reason, f"reason={reason} should contain 'in_use'"


def test_find_free_port_raises_on_no_free_ports():
    ports_in_use = []
    sockets = []
    try:
        for i in range(5):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("localhost", 0))
            p = s.getsockname()[1]
            s.listen(1)
            sockets.append(s)
            ports_in_use.append(p)
        base = min(ports_in_use)
        with pytest.raises(RuntimeError, match="No free port found"):
            _find_free_port("localhost", base, max_port=base)
    finally:
        for s in sockets:
            try:
                s.close()
            except Exception:
                pass
