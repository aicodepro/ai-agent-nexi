"""Live free-model discovery — no hardcoded lists (Darsh: providers add/remove
free models, so NEXI must read what's free right now and route by task).

Live HTTP is blocked in the tool sandbox, so the network call is mocked with a
realistic OpenRouter /models payload; these assert the free-filtering, task
categorization, caching, and non-blocking hot-path read are correct.
"""
import os
import sys
import time
import threading

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.agent_runtime import model_discovery as md


# a realistic slice of the real OpenRouter catalogue (free + paid mixed)
CATALOGUE = {
    "data": [
        {"id": "cohere/north-mini-code:free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "nvidia/nemotron-3-ultra:free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "tencent/hy3:free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "deepseek/deepseek-v3", "pricing": {"prompt": "0", "completion": "0.5"}},  # NOT free (paid completion)
        {"id": "anthropic/claude-sonnet-5", "pricing": {"prompt": "3", "completion": "15"}},  # paid
        {"id": "qwen/qwen-2.5-coder:free", "pricing": {"prompt": "0", "completion": "0"}},
    ]
}


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    md._CACHE.clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    yield
    md._CACHE.clear()


def _mock_ok(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return CATALOGUE

    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())


def test_only_truly_free_models_are_discovered(monkeypatch):
    _mock_ok(monkeypatch)
    free = md.discover_free_models("openrouter", force=True)
    assert "cohere/north-mini-code:free" in free
    assert "qwen/qwen-2.5-coder:free" in free
    # paid-completion and fully-paid models excluded
    assert "deepseek/deepseek-v3" not in free
    assert "anthropic/claude-sonnet-5" not in free


def test_task_categorization_routes_code_and_reasoning(monkeypatch):
    _mock_ok(monkeypatch)
    md.discover_free_models("openrouter", force=True)
    code = md.free_models_for_task("openrouter", "code", limit=3)
    assert any("coder" in m or "code" in m for m in code[:2]), code
    orch = md.free_models_for_task("openrouter", "orchestration", limit=3)
    assert any("nemotron" in m or "ultra" in m for m in orch[:2]), orch


def test_hot_path_read_is_non_blocking_and_never_calls_network(monkeypatch):
    """discovered_cached must NOT hit the network — that's the whole point of warming."""
    def _boom(*a, **k):
        raise AssertionError("network call in the hot path")

    monkeypatch.setattr("requests.get", _boom)
    assert md.discovered_cached("openrouter") == []   # cold cache -> empty, no call


def test_cache_is_reused_within_ttl(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        def json(self):
            return CATALOGUE

    def _counting_get(*a, **k):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr("requests.get", _counting_get)
    md.discover_free_models("openrouter", force=True)
    md.discover_free_models("openrouter")   # within TTL -> cached, no 2nd call
    assert calls["n"] == 1


def test_concurrent_discovery_populates_cache_once(monkeypatch):
    calls = {"n": 0}
    calls_lock = threading.Lock()

    class _Resp:
        status_code = 200

        def json(self):
            return CATALOGUE

    def _slow_get(*_args, **_kwargs):
        with calls_lock:
            calls["n"] += 1
        time.sleep(0.05)
        return _Resp()

    monkeypatch.setattr("requests.get", _slow_get)
    start = threading.Barrier(6)
    threads = [threading.Thread(target=lambda: (start.wait(), md.discover_free_models("openrouter"))) for _ in range(5)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert calls["n"] == 1


def test_offline_falls_back_to_empty_not_crash(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("offline")

    monkeypatch.setattr("requests.get", _boom)
    assert md.discover_free_models("openrouter", force=True) == []


def test_policy_uses_discovered_models_when_cache_is_warm(monkeypatch):
    """model_policy must prefer LIVE free models over its static pool once warmed."""
    from engine.agent_runtime import model_policy as mp
    _mock_ok(monkeypatch)
    md.discover_free_models("openrouter", force=True)   # warm the cache
    chain = mp.model_chain("openrouter", "code")
    # the live coder model should now appear (not just the static defaults)
    assert any("coder" in m for m in chain), chain
