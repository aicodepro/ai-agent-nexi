"""Per-runtime, free-first model selection with fallback (Darsh's correction).

The rule NEXI must follow: do NOT default to one global model (explicitly not
gemini-2.5-flash). Each runtime switches within its OWN pool — claude-code across
Sonnet/Opus/Fable, opencode/Hermes across their free pools — free models first, and
a task resolves to a fallback CHAIN so a failing model has somewhere to fall back to.
OpenRouter is free-models-only here.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.agent_runtime import model_policy as mp


def test_a_task_resolves_to_a_chain_not_a_single_model():
    chain = mp.model_chain("claude-code", "orchestration")
    assert len(chain) >= 2, "must have fallbacks, not one model"
    assert chain[0] == "claude-opus-4-8", "task preference goes first"


def test_claude_code_switches_within_the_claude_family():
    chain = mp.model_chain("claude-code", "quick")
    assert chain[0] == "claude-haiku-4-5"
    assert set(chain) <= {"claude-sonnet-5", "claude-opus-4-8", "claude-fable-5", "claude-haiku-4-5"}
    assert "gemini" not in " ".join(chain), "no gemini default — Darsh ruled it out"


def test_no_global_gemini_default_anywhere():
    for rt in mp.POOLS:
        for task in (None, "code", "orchestration"):
            first = mp.select_model(rt, task) or ""
            assert "gemini-2.5-flash" not in first, f"{rt}/{task} defaulted to gemini-2.5-flash"


def test_free_models_come_before_paid(monkeypatch):
    # a pool where only some are free -> free ones must lead the fallback order
    monkeypatch.setitem(mp.POOLS, "tmp", {
        "models": ["paid/a", "free/b", "paid/c", "free/d"],
        "free": ["free/b", "free/d"], "tasks": {}, "env": "TMP_MODELS",
    })
    chain = mp.model_chain("tmp")
    assert chain.index("free/b") < chain.index("paid/a")
    assert chain.index("free/d") < chain.index("paid/c")


def test_openrouter_chain_is_free_models_only():
    for m in mp.model_chain("openrouter"):
        assert m.endswith(":free"), f"OpenRouter chain has a non-free model: {m}"


def test_env_override_replaces_the_pool(monkeypatch):
    monkeypatch.setenv("NEXI_OPENCODE_MODELS", "acme/one, acme/two")
    chain = mp.model_chain("opencode")
    assert chain[:2] == ["acme/one", "acme/two"]


def test_task_preference_ignored_if_not_in_overridden_pool(monkeypatch):
    """If the operator overrides the pool and the task's preferred id isn't in it,
    selection must not resurrect the old preferred model."""
    monkeypatch.setenv("NEXI_CLAUDE_CODE_MODELS", "only/model")
    assert mp.model_chain("claude-code", "orchestration") == ["only/model"]


def test_unknown_runtime_is_empty_not_a_crash():
    assert mp.model_chain("does-not-exist") == []
    assert mp.select_model("does-not-exist") is None


def test_model_discovery_warm_flag_is_thread_safe(monkeypatch):
    assert hasattr(mp, "_WARM_LOCK")
    calls = {"n": 0}
    calls_lock = threading.Lock()

    def slow_warm():
        with calls_lock:
            calls["n"] += 1
        time.sleep(0.05)

    monkeypatch.setattr(mp, "warm_discovery", slow_warm)
    monkeypatch.setattr(mp, "_WARMED", False)
    start = threading.Barrier(6)
    threads = [threading.Thread(target=lambda: (start.wait(), mp._warm_once())) for _ in range(5)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert calls["n"] == 1


def test_model_ranking_benchmark_reads_do_not_race_refresh(monkeypatch):
    from engine.agent_runtime import model_ranking

    read_started = threading.Event()
    release_read = threading.Event()
    write_happened = threading.Event()

    class BlockingBenchmarks(dict):
        def items(self):
            for index, item in enumerate(super().items()):
                if index == 0:
                    read_started.set()
                    release_read.wait(timeout=2)
                yield item

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            write_happened.set()

    monkeypatch.setattr(model_ranking, "BENCHMARKS", BlockingBenchmarks({"first": 1, "second": 2}))
    errors = []
    scorer = threading.Thread(target=lambda: _capture_error(errors, lambda: model_ranking.score("unknown")))
    scorer.start()
    assert read_started.wait(timeout=1)
    refresher = threading.Thread(target=lambda: model_ranking.refresh_benchmarks({"new": 3}))
    refresher.start()
    write_happened.wait(timeout=0.1)
    release_read.set()
    scorer.join(timeout=2)
    refresher.join(timeout=2)

    assert errors == []


def _capture_error(errors, fn):
    try:
        fn()
    except Exception as exc:
        errors.append(exc)


def test_model_discovery_subprocess_uses_direct_argv(monkeypatch):
    from engine.agent_runtime import model_ranking

    captured = {}

    class Result:
        stdout = "provider/model\n"

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["shell"] = kwargs.get("shell", False)
        return Result()

    monkeypatch.setattr(model_ranking.subprocess, "run", fake_run)
    model_ranking._CACHE.clear()

    assert model_ranking.discover_cli_models("opencode", force=True) == ["provider/model"]
    assert captured == {"argv": ["opencode", "models"], "shell": False}


# ---- self-healing: a failed model drops out of selection -----------------------

def test_a_downed_model_is_skipped_and_the_next_is_chosen(monkeypatch):
    from engine.agent_runtime import model_health
    model_health.reset("opencode")
    monkeypatch.setenv("NEXI_MODEL_FAIL_THRESHOLD", "1")   # trip on first failure

    first = mp.select_model("opencode", "code")
    assert first  # some free model
    model_health.mark_failed("opencode", first, "provider_unavailable")

    second = mp.select_model("opencode", "code")
    assert second and second != first, "downed model must not be re-selected"
    model_health.reset("opencode")


def test_recovery_clears_the_bench(monkeypatch):
    from engine.agent_runtime import model_health
    model_health.reset("opencode")
    monkeypatch.setenv("NEXI_MODEL_FAIL_THRESHOLD", "1")
    m = mp.select_model("opencode")
    model_health.mark_failed("opencode", m, "timeout")
    assert m not in mp.model_chain("opencode")   # benched
    model_health.mark_ok("opencode", m)          # recovered
    assert m in mp.model_chain("opencode")        # back in rotation
    model_health.reset("opencode")


def test_all_models_down_still_returns_something(monkeypatch):
    """A total bench must not strand the runtime with no model to try."""
    from engine.agent_runtime import model_health
    model_health.reset("openrouter")
    monkeypatch.setenv("NEXI_MODEL_FAIL_THRESHOLD", "1")
    for m in mp.model_chain("openrouter", exclude_down=False):
        model_health.mark_failed("openrouter", m, "error")
    chain = mp.model_chain("openrouter")
    assert chain, "must fall back to the full pool rather than return nothing"
    model_health.reset("openrouter")
