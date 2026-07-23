"""Forge loop end-to-end (engine/forge/forge_engine.py) with a fake generator."""
import pytest
import json
from pathlib import Path

from engine.forge import forge_engine, tool_installer


def _fake(payload):
    def gen(_prompt):
        return json.dumps(payload)
    return gen


GOOD = {
    "name": "add_numbers",
    "function_code": "def add_numbers(a, b):\n    return a + b\n",
    "test_code": "from forged_tool import add_numbers\n\ndef test_add():\n    assert add_numbers(2, 3) == 5\n",
}
BAD = {
    "name": "add_numbers",
    "function_code": "def add_numbers(a, b):\n    return a + b\n",
    "test_code": "from forged_tool import add_numbers\n\ndef test_add():\n    assert add_numbers(2, 3) == 999\n",
}
RISKY = {
    "name": "list_dir",
    "function_code": "import os\n\ndef list_dir(path='.'):\n    return os.listdir(path)\n",
    "test_code": "from forged_tool import list_dir\n\ndef test_list():\n    assert isinstance(list_dir('.'), list)\n",
}


def test_good_safe_tool_forges_installs_and_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    r = forge_engine.forge_tool("add two numbers", generate_fn=_fake(GOOD))
    assert r["ok"] is True and r["status"] == "installed" and r["name"] == "add_numbers"
    assert "add_numbers" in tool_installer.list_forged()
    assert tool_installer.call_forged("add_numbers", 4, 5) == 9   # the forged tool actually works
    assert tool_installer.remove("add_numbers") is True


def test_failing_tool_is_rejected_after_retries(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    r = forge_engine.forge_tool("broken", generate_fn=_fake(BAD), max_retries=1)
    assert r["ok"] is False and r["status"] == "failed"
    assert tool_installer.list_forged() == []


def test_risky_tool_needs_approval_not_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    r = forge_engine.forge_tool("list a directory", generate_fn=_fake(RISKY))
    assert r["ok"] is False and r["status"] == "needs_approval"
    assert "list_dir" not in tool_installer.list_forged()


def test_empty_spec_fails():
    assert forge_engine.forge_tool("  ")["status"] == "failed"


def test_risky_code_is_never_executed(monkeypatch, tmp_path):
    """The sandbox is process isolation + a timeout, NOT a container. So code the
    static scan already flagged must never reach sandbox_runner at all — gate first,
    execute second."""
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    ran = {"called": False}

    def boom(*_a, **_k):
        ran["called"] = True
        raise AssertionError("flagged code must never be executed")

    monkeypatch.setattr(forge_engine.sandbox_runner, "run_test", boom)
    r = forge_engine.forge_tool("list a directory", generate_fn=_fake(RISKY))

    assert r["status"] == "needs_approval"
    assert ran["called"] is False, "risky generated code was executed before being gated"


def test_default_generator_does_not_use_the_chat_brain(monkeypatch):
    """Regression: _default_generate used to call the Gemini CHAT brain, which
    injects persona + memory and answers in prose — so every real forge died on
    JSONDecodeError and no tool was ever installed. It must ask a JSON-capable
    provider in strict-JSON mode instead."""
    from engine.forge import code_generator

    calls = {"provider": 0}

    class _Result:
        ok = True
        raw_text = json.dumps(GOOD)
        decision = None

    class _Provider:
        def is_available(self):
            return True

        def route_with_schema(self, messages, schema, *, model="", timeout=4.0):
            calls["provider"] += 1
            # strict-JSON instruction must be present, or json_object mode misbehaves
            assert any("JSON" in str(m.get("content", "")) for m in messages)
            return _Result()

    monkeypatch.setattr("engine.providers.get_intent_provider", lambda *_a, **_k: _Provider())

    def _brain_must_not_run(*_a, **_k):
        raise AssertionError("the conversational brain must not generate tool code")

    monkeypatch.setattr("engine.gemini_brain.ask_gemini", _brain_must_not_run, raising=False)

    out = code_generator.generate("add two numbers")
    assert calls["provider"] == 1
    assert out["name"] == "add_numbers"
    assert "def add_numbers" in out["function_code"]


def test_generated_name_is_sanitized_for_install_call_and_remove(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    payload = {
        "name": "../../123 bad-tool",
        "function_code": "def _123_bad_tool(value):\n    return value + 1\n",
        "test_code": "from forged_tool import _123_bad_tool\n\ndef test_tool():\n    assert _123_bad_tool(1) == 2\n",
    }

    result = forge_engine.forge_tool("increment", generate_fn=_fake(payload), max_retries=0)

    assert result["ok"] is True
    assert result["name"] == "_123_bad_tool"
    assert Path(result["path"]).resolve().parent == tmp_path.resolve()
    assert tool_installer.call_forged("../../123 bad-tool", 2) == 3
    assert tool_installer.remove("../../123 bad-tool") is True


def test_provider_failure_is_actionable_and_never_falls_back_to_chat_brain(monkeypatch):
    from engine.forge import code_generator

    class _Provider:
        def is_available(self):
            return True

        def route_with_schema(self, *_args, **_kwargs):
            raise TimeoutError("provider timed out")

    monkeypatch.setattr("engine.providers.get_intent_provider", lambda: _Provider())
    monkeypatch.setattr(
        "engine.gemini_brain.ask_gemini",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("chat fallback must not run")),
        raising=False,
    )

    with pytest.raises(code_generator.CodeGenerationError, match="provider.*timed out"):
        code_generator.generate("add two numbers")


@pytest.mark.parametrize(
    "stage,patch_target",
    [
        ("sandbox", "sandbox_runner.run_test"),
        ("verification", "holdout_eval.evaluate"),
        ("install", "tool_installer.install"),
    ],
)
def test_forge_operation_exceptions_return_structured_failure(monkeypatch, tmp_path, stage, patch_target):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    monkeypatch.setattr(forge_engine.sandbox_runner, "run_test", lambda *_a, **_k: {"passed": True, "output": ""})
    monkeypatch.setattr(forge_engine.holdout_eval, "evaluate", lambda *_a, **_k: {"ok": True, "reason": "verified"})

    owner, attribute = patch_target.split(".")
    monkeypatch.setattr(
        getattr(forge_engine, owner),
        attribute,
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(f"{stage} unavailable")),
    )

    result = forge_engine.forge_tool("add", generate_fn=_fake(GOOD), max_retries=0)

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error"]["stage"] == stage
    assert f"{stage} unavailable" in result["error"]["message"]


def test_archive_failure_is_reported_without_claiming_rollback_archive(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    monkeypatch.setattr(forge_engine.sandbox_runner, "run_test", lambda *_a, **_k: {"passed": True, "output": ""})
    monkeypatch.setattr(forge_engine.holdout_eval, "evaluate", lambda *_a, **_k: {"ok": True, "reason": "verified"})
    monkeypatch.setattr(
        forge_engine.archive,
        "record",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("archive disk full")),
    )

    result = forge_engine.forge_tool("add", generate_fn=_fake(GOOD), max_retries=0)

    assert result["ok"] is True
    assert result["archived"] is False
    assert result["archive_error"]["type"] == "OSError"
    assert "not archived" in result["message"].lower()
    assert "Archived for rollback" not in result["message"]


@pytest.mark.parametrize("label,code", [
    ("getattr_builtins", "getattr(__builtins__, '__import__')('os').system('calc')"),
    ("subclasses_walk", "x = ().__class__.__bases__[0].__subclasses__()"),
    ("globals_reach", "def f():\n    return f.__globals__\n"),
    ("lambda_import", "g = (lambda: __import__('os'))"),
    ("setattr_reflection", "setattr(object, 'x', 1)"),
])
def test_scan_blocks_ast_allowlist_bypasses(label, code):
    """The AST scan must flag reflective sandbox-escapes (getattr/__builtins__/
    dunder traversal), not just literal eval/open/import. A green scan on any of
    these = host RCE, because forge auto-installs 'safe' tools and even the sandbox
    is not a container. Forge gates on scan BEFORE executing, so a flag = never run."""
    from engine.forge import safety_scan
    result = safety_scan.scan(code)
    assert result["safe"] is False, f"{label!r} bypassed the scan: {result}"


@pytest.mark.parametrize("code", [
    "def add(a, b):\n    return a + b\n",
    "import json\ndef d(x):\n    return json.dumps(x)\n",
    "def c2f(c):\n    return c * 9 / 5 + 32\n",
])
def test_scan_keeps_pure_compute_safe(code):
    from engine.forge import safety_scan
    assert safety_scan.scan(code)["safe"] is True
