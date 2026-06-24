import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.hotword_engine_manager import HotwordEngineManager, _env_int


def _saved_env():
    """Return saved env vars for later restore."""
    keys = ["OPENWAKEWORD_CONSECUTIVE_HITS", "OPENWAKEWORD_SCORE_THRESHOLD",
            "NEXI_HOTWORD_COOLDOWN_MS", "NEXI_HOTWORD_MIN_RMS",
            "NEXI_HOTWORD_RISING_EDGE_DELTA"]
    return {k: os.environ.pop(k, None) for k in keys}


def _restore_env(saved: dict):
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def test_consecutive_hits_defaults_to_one():
    saved = _saved_env()
    try:
        engine = HotwordEngineManager(config={})
        assert engine.consecutive_hits_required == 1
    finally:
        _restore_env(saved)


def test_consecutive_hits_env_override():
    saved = _saved_env()
    try:
        os.environ["OPENWAKEWORD_CONSECUTIVE_HITS"] = "1"
        engine = HotwordEngineManager(config={"enabled": False})
        assert engine.consecutive_hits_required == 1
    finally:
        _restore_env(saved)


def test_consecutive_hits_env_set_to_two():
    saved = _saved_env()
    try:
        os.environ["OPENWAKEWORD_CONSECUTIVE_HITS"] = "2"
        engine = HotwordEngineManager(config={"enabled": False})
        assert engine.consecutive_hits_required == 2
    finally:
        _restore_env(saved)


def test_threshold_default():
    saved = _saved_env()
    try:
        engine = HotwordEngineManager(config={"enabled": False})
        assert engine.threshold == 0.25
    finally:
        _restore_env(saved)


def test_threshold_env_override():
    saved = _saved_env()
    try:
        os.environ["OPENWAKEWORD_SCORE_THRESHOLD"] = "0.5"
        engine = HotwordEngineManager(config={"enabled": False})
        assert engine.threshold == 0.5
    finally:
        _restore_env(saved)


def test_min_rms_default():
    saved = _saved_env()
    try:
        engine = HotwordEngineManager(config={"enabled": False})
        assert engine.min_rms == 0.003
    finally:
        _restore_env(saved)


def test_cooldown_ms_default():
    saved = _saved_env()
    try:
        engine = HotwordEngineManager(config={"enabled": False})
        assert engine.cooldown_ms == 1500
    finally:
        _restore_env(saved)
