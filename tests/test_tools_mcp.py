import pytest
from tools.mcp import _load_servers


def test_load_servers_returns_dict():
    servers = _load_servers()
    assert isinstance(servers, dict)
