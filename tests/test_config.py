from core.config import cfg, __version__, env_bool, env_int, NexiConfig


def test_config_has_defaults():
    assert hasattr(cfg, "name")
    assert cfg.name == "Nexi"
    assert hasattr(cfg, "version")
    assert cfg.version == __version__
    assert hasattr(cfg, "hotword_enabled")
    assert hasattr(cfg, "asr_provider")
    assert hasattr(cfg, "brain_provider")
    assert hasattr(cfg, "ui_mode")
    assert hasattr(cfg, "gemini_model_chain")
    assert hasattr(cfg, "tts_providers")


def test_env_bool_true():
    assert env_bool("NEXI_HOTWORD_ENABLED", True) is True


def test_env_bool_false():
    assert env_bool("NONEXISTENT_VAR_THAT_NEVER_EXISTS", False) is False


def test_env_int_default():
    assert env_int("NONEXISTENT_INT_VAR", 42) == 42


def test_env_int_invalid():
    assert env_int("NONEXISTENT_INT_VAR", 10) == 10


def test_version():
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_config_gemini_model_chain_defaults():
    chain = cfg.gemini_model_chain
    assert isinstance(chain, list)
    assert len(chain) >= 2
    assert chain[0] == cfg.gemini_model_primary


def test_config_tts_providers_defaults():
    providers = cfg.tts_providers
    assert isinstance(providers, list)
    assert len(providers) > 0


def test_config_properties_return_strings():
    assert isinstance(cfg.gemini_api_key, str)
    assert isinstance(cfg.groq_api_key, str)


def test_nexiconfig_standalone():
    nc = NexiConfig()
    assert nc.name == "Nexi"
    assert nc.version == __version__
