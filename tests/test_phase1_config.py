from core.config import cfg


def test_jarvis_config_defaults():
    assert cfg.jarvis.jarvis_enabled is True
    assert cfg.jarvis.jarvis_max_tool_steps == 10


def test_jarvis_config_provider_defaults():
    assert cfg.jarvis.jarvis_brain_provider == "gemini"


def test_jarvis_config_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_ENABLED", "false")
    from core.config import NexiConfig
    cfg_reload = NexiConfig()
    assert cfg_reload.jarvis.jarvis_enabled is False
