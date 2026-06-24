from core.config import cfg


def test_nexi_config_defaults():
    assert cfg.nexi.nexi_enabled is True
    assert cfg.nexi.nexi_max_tool_steps == 10


def test_nexi_config_provider_defaults():
    assert cfg.nexi.nexi_brain_provider == "gemini"


def test_nexi_config_env_override(monkeypatch):
    monkeypatch.setenv("NEXI_ENABLED", "false")
    from core.config import NexiConfig
    cfg_reload = NexiConfig()
    assert cfg_reload.nexi.nexi_enabled is False
