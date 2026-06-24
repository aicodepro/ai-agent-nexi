import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_demo_check():
    path = ROOT / "scripts" / "demo_check.py"
    spec = importlib.util.spec_from_file_location("demo_check", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["demo_check"] = module
    spec.loader.exec_module(module)
    return module


def test_demo_check_run_checks_returns_summary(monkeypatch):
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    module = _load_demo_check()
    summary = module.run_checks(strict=False)
    assert summary["failed"] == 0
    assert summary["passed"] >= 6
    assert len(summary["results"]) == 8


def test_demo_check_json_safe(monkeypatch):
    import json

    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    module = _load_demo_check()
    summary = module.run_checks(strict=False)
    json.dumps(summary)


def test_demo_check_main_returns_zero(monkeypatch):
    monkeypatch.setenv("GROQ_INTENT_V2_ENABLED", "false")
    module = _load_demo_check()
    assert module.main(["--json"]) == 0
