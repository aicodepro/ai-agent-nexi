import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_model_router_defaults_use_gpt_oss_for_intent(monkeypatch):
    from engine.groq_intent_planner import get_model_config
    monkeypatch.delenv("GROQ_INTENT_MODEL", raising=False)
    config = get_model_config()
    assert config["intent_model"] == "openai/gpt-oss-20b"
    assert config["intent_model_fallback"] == "qwen/qwen3-32b"


def test_strong_and_safety_model_defaults(monkeypatch):
    from engine.groq_intent_planner import get_model_config
    monkeypatch.delenv("GROQ_INTENT_MODEL_STRONG", raising=False)
    monkeypatch.delenv("SAFETY_MODEL", raising=False)
    config = get_model_config()
    assert config["intent_model_strong"] == "openai/gpt-oss-120b"
    assert config["safety_model"] == "openai/gpt-oss-safeguard-20b"


def test_speech_tts_and_vision_defaults(monkeypatch):
    from engine.groq_intent_planner import get_model_config
    for key in ("ASR_MODEL", "TTS_MODEL", "VISION_MODEL"):
        monkeypatch.delenv(key, raising=False)
    config = get_model_config()
    assert config["asr_model"] == "whisper-large-v3-turbo"
    assert config["tts_model"] == "orpheus-english"
    assert config["vision_model"] == "meta-llama/llama-4-scout-17b-16e-instruct"
