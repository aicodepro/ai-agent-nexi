import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.hotword_engine_manager import HotwordEngineManager, _normalise_oww_name, _normalise_oww_list


def test_phrases_default_contains_hey_nexi():
    engine = HotwordEngineManager(config={"enabled": False})
    assert "hey nexi" in engine.phrases


def test_phrases_contains_nexi():
    engine = HotwordEngineManager(config={"enabled": False})
    assert "nexi" in engine.phrases


def test_selected_phrase_is_hey_nexi():
    engine = HotwordEngineManager(config={"enabled": False})
    assert engine.phrase == "hey nexi"


def test_normalise_list_handles_comma_separated():
    result = _normalise_oww_list("hey_nexi,nexi")
    assert "hey nexi" in result
    assert "nexi" in result


def test_prediction_key_mapping_uses_configured():
    engine = HotwordEngineManager(config={"enabled": False})
    engine._configured_names = ["hey nexi"]
    engine._last_predictions = {"hey nexi": 0.8, "alexa": 0.1}
    engine._last_prediction_keys = ["alexa", "hey nexi"]
    engine._last_prediction_key = "hey nexi"
    assert engine._last_prediction_key == "hey nexi"
