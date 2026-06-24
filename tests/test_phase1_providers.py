from core.tts import _get_tts_provider
from core.asr import _get_asr_provider
from brain.gemini import _get_brain_config
from core.config import cfg


def test_tts_provider_contains_groq():
    assert "groq" in _get_tts_provider()


def test_tts_provider_is_string():
    assert isinstance(_get_tts_provider(), str)


def test_asr_provider_defaults_to_groq():
    assert _get_asr_provider() == "groq"


def test_asr_provider_is_string():
    assert isinstance(_get_asr_provider(), str)


def test_brain_config_defaults_to_gemini():
    config = _get_brain_config()
    assert "googleapis" in config["api_base"] or "gemini" in config["api_base"].lower()


def test_brain_config_claude(monkeypatch):
    monkeypatch.setattr(cfg.nexi, "nexi_brain_provider", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
    config = _get_brain_config()
    assert "anthropic.com" in config["api_base"]
    assert config["model"] == "claude-opus-4-8"
    assert config["api_key"] == "sk-ant-test123"


def test_brain_config_deepseek(monkeypatch):
    monkeypatch.setattr(cfg.nexi, "nexi_brain_provider", "deepseek")
    config = _get_brain_config()
    assert "deepseek.com" in config["api_base"]
    assert config["model"] == "deepseek-v4-pro"
