import os
import sys
import io
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.hotword_engine_manager import HotwordEngineManager, _normalise_oww_name


def test_log_status_contains_hotword_config():
    engine = HotwordEngineManager(config={"enabled": False})
    log_lines = []
    original_log = engine.log_status
    engine._last_prediction_keys = ["hey nexi"]
    engine._last_prediction_key = "hey nexi"
    engine._model_name = "hey_nexi_v0.1.onnx"
    buffer = io.StringIO()
    import sys as _sys
    old_stdout = _sys.stdout
    _sys.stdout = buffer
    try:
        engine.log_status()
    finally:
        _sys.stdout = old_stdout
    output = buffer.getvalue()
    assert "[HOTWORD_CONFIG]" in output
    assert "threshold=" in output
    assert "consecutive_hits=" in output
    assert "cooldown_ms=" in output


def test_log_status_contains_model_path():
    engine = HotwordEngineManager(config={"enabled": False})
    buffer = io.StringIO()
    import sys as _sys
    old_stdout = _sys.stdout
    _sys.stdout = buffer
    try:
        engine.log_status()
    finally:
        _sys.stdout = old_stdout
    output = buffer.getvalue()
    assert "[HOTWORD] model_path=" in output


def test_normalise_oww_name_handles_onnx():
    assert _normalise_oww_name("hey_nexi_v0.1.onnx") == "hey_nexi_v0.1.onnx"


def test_normalise_oww_name_converts_underscores():
    assert _normalise_oww_name("hey_nexi") == "hey nexi"
