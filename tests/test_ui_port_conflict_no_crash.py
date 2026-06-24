import os
import sys
import socket
import threading
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import _is_port_available, _find_free_port


def test_port_conflict_does_not_crash():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 8010))
        s.listen(1)
        try:
            selected, reason = _find_free_port("localhost", 8010, max_port=8020)
            assert selected != 8010
            assert "in_use" in reason or selected > 8010
        finally:
            s.close()
        time.sleep(0.05)


def test_port_conflict_no_socket_error():
    env_backup = os.environ.copy()
    os.environ["NEXI_UI_AUTO_PORT"] = "false"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 8011))
            s.listen(1)
            selected, reason = _find_free_port("localhost", 8011)
            assert selected == 8011
            assert reason == "in_use_but_auto_disabled"
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_port_conflict_two_in_a_row():
    sockets = []
    try:
        for port in [8012, 8013]:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("localhost", port))
            s.listen(1)
            sockets.append(s)
        selected, reason = _find_free_port("localhost", 8012, max_port=8020)
        assert selected >= 8014 or "in_use" in reason
    finally:
        for s in sockets:
            try:
                s.close()
            except Exception:
                pass
