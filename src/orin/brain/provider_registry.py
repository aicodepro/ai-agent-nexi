import json
import os
import threading

PRIVACY_MODES = ("normal", "private", "local_only")

CLOUD_PROVIDER_NAMES = {
    "deepseek", "openai", "anthropic", "google", "huggingface",
}

DEFAULT_PROVIDERS = {
    "deepseek_v4_pro": {
        "provider_name": "deepseek",
        "model_name": "deepseek_v4_pro",
        "enabled": True,
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "supports_vision": True,
        "supports_streaming": True,
        "supports_tools": False,
        "supports_long_context": False,
        "is_cloud": True,
        "timeout_seconds": 120,
    },
    "deepseek_r1": {
        "provider_name": "deepseek",
        "model_name": "deepseek_r1",
        "enabled": True,
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "supports_vision": False,
        "supports_streaming": True,
        "supports_tools": False,
        "supports_long_context": True,
        "is_cloud": True,
        "timeout_seconds": 120,
    },
    "deepseek_v3_2": {
        "provider_name": "deepseek",
        "model_name": "deepseek_v3_2",
        "enabled": True,
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "supports_vision": False,
        "supports_streaming": True,
        "supports_tools": False,
        "supports_long_context": False,
        "is_cloud": True,
        "timeout_seconds": 30,
    },
    "glm_5_1": {
        "provider_name": "glm",
        "model_name": "glm_5_1",
        "enabled": True,
        "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_key_env": "GLM_API_KEY",
        "supports_vision": True,
        "supports_streaming": True,
        "supports_tools": True,
        "supports_long_context": True,
        "is_cloud": True,
        "timeout_seconds": 60,
    },
    "minimax_2_7": {
        "provider_name": "minimax",
        "model_name": "minimax_2_7",
        "enabled": True,
        "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "api_key_env": "MINIMAX_API_KEY",
        "supports_vision": False,
        "supports_streaming": True,
        "supports_tools": False,
        "supports_long_context": True,
        "is_cloud": True,
        "timeout_seconds": 45,
    },
    "qwen3": {
        "provider_name": "qwen",
        "model_name": "qwen3",
        "enabled": True,
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "api_key_env": "QWEN_API_KEY",
        "supports_vision": True,
        "supports_streaming": True,
        "supports_tools": True,
        "supports_long_context": True,
        "is_cloud": True,
        "timeout_seconds": 15,
    },
    "kimi_2_6": {
        "provider_name": "kimi",
        "model_name": "kimi_2_6",
        "enabled": True,
        "endpoint": "https://api.moonshot.cn/v1/chat/completions",
        "api_key_env": "KIMI_API_KEY",
        "supports_vision": True,
        "supports_streaming": True,
        "supports_tools": False,
        "supports_long_context": True,
        "is_cloud": True,
        "timeout_seconds": 90,
    },
    "mimo": {
        "provider_name": "mimo",
        "model_name": "mimo",
        "enabled": False,
        "endpoint": "",
        "api_key_env": "MIMO_API_KEY",
        "supports_vision": False,
        "supports_streaming": False,
        "supports_tools": False,
        "supports_long_context": False,
        "is_cloud": True,
        "timeout_seconds": 30,
    },
}


class ProviderRegistry:
    _providers = {}
    _lock = threading.Lock()

    @classmethod
    def load_defaults(cls):
        with cls._lock:
            cls._providers = {}
            for model_key, config in DEFAULT_PROVIDERS.items():
                cls._providers[model_key] = dict(config)

    @classmethod
    def load_from_file(cls, filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
        loaded = 0
        with cls._lock:
            for entry in data:
                model_key = entry.get("model_name")
                if not model_key:
                    continue
                if cls._validate_entry(entry):
                    cls._providers[model_key] = entry
                    loaded += 1
        return loaded

    @classmethod
    def _validate_entry(cls, entry):
        required = {"provider_name", "model_name", "endpoint", "api_key_env"}
        if not all(k in entry for k in required):
            return False
        if not isinstance(entry.get("enabled", True), bool):
            return False
        return True

    @classmethod
    def get_provider(cls, model_name):
        with cls._lock:
            return cls._providers.get(model_name)

    @classmethod
    def is_enabled(cls, model_name):
        provider = cls.get_provider(model_name)
        if provider is None:
            return False
        return provider.get("enabled", False)

    @classmethod
    def is_cloud(cls, model_name):
        provider = cls.get_provider(model_name)
        if provider is None:
            return True
        return provider.get("is_cloud", True)

    @classmethod
    def enable(cls, model_name):
        with cls._lock:
            provider = cls._providers.get(model_name)
            if provider:
                provider["enabled"] = True
                return True
            return False

    @classmethod
    def disable(cls, model_name):
        with cls._lock:
            provider = cls._providers.get(model_name)
            if provider:
                provider["enabled"] = False
                return True
            return False

    @classmethod
    def set_enabled_batch(cls, enabled_list, disabled_list=None):
        with cls._lock:
            for model_name in enabled_list:
                provider = cls._providers.get(model_name)
                if provider:
                    provider["enabled"] = True
            if disabled_list:
                for model_name in disabled_list:
                    provider = cls._providers.get(model_name)
                    if provider:
                        provider["enabled"] = False

    @classmethod
    def list_providers(cls):
        with cls._lock:
            return {k: dict(v) for k, v in cls._providers.items()}

    @classmethod
    def list_enabled_models(cls):
        with cls._lock:
            return [k for k, v in cls._providers.items() if v.get("enabled", False)]

    @classmethod
    def list_model_names(cls):
        with cls._lock:
            return list(cls._providers.keys())

    @classmethod
    def count_providers(cls):
        with cls._lock:
            return len(cls._providers)

    @classmethod
    def get_api_key_env(cls, model_name):
        provider = cls.get_provider(model_name)
        if provider is None:
            return None
        return provider.get("api_key_env")

    @classmethod
    def resolve_api_key(cls, model_name):
        env_var = cls.get_api_key_env(model_name)
        if env_var is None:
            return None
        return os.environ.get(env_var)

    @classmethod
    def check_api_key_available(cls, model_name):
        return cls.resolve_api_key(model_name) is not None

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._providers.clear()


ProviderRegistry.load_defaults()
