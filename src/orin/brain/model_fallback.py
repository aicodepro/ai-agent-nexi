from src.orin.brain.provider_registry import ProviderRegistry
from src.orin.brain.model_policy import ROUTING_POLICY


_FALLBACK_CHAIN_CACHE = {}


def build_fallback_chain(task_type):
    if task_type in _FALLBACK_CHAIN_CACHE:
        return _FALLBACK_CHAIN_CACHE[task_type]
    policy = ROUTING_POLICY.get(task_type)
    if policy is None:
        chain = []
    else:
        seen = set()
        chain = []
        preferred = policy["preferred"]
        fallback = policy["fallback"]
        if preferred not in seen:
            chain.append(preferred)
            seen.add(preferred)
        if fallback not in seen:
            chain.append(fallback)
            seen.add(fallback)
        for name in ("deepseek_v4_pro", "deepseek_r1", "deepseek_v3_2",
                     "glm_5_1", "kimi_2_6", "minimax_2_7", "qwen3"):
            if name not in seen:
                chain.append(name)
                seen.add(name)
    _FALLBACK_CHAIN_CACHE[task_type] = chain
    return chain


def resolve_model(task_type, privacy_mode="normal"):
    policy = ROUTING_POLICY.get(task_type)
    if policy is None:
        return None, "Unknown task type"
    chain = build_fallback_chain(task_type)
    for model_name in chain:
        if not ProviderRegistry.is_enabled(model_name):
            continue
        provider = ProviderRegistry.get_provider(model_name)
        if provider is None:
            continue
        is_cloud = provider.get("is_cloud", True)
        if privacy_mode == "local_only" and is_cloud:
            continue
        if privacy_mode == "private" and is_cloud:
            env_key = provider.get("api_key_env", "")
            import os
            if not os.environ.get(env_key):
                continue
        return model_name, ""
    return None, "No available model for task type and privacy mode"


def is_available(model_name, privacy_mode="normal"):
    if not ProviderRegistry.is_enabled(model_name):
        return False
    provider = ProviderRegistry.get_provider(model_name)
    if provider is None:
        return False
    if privacy_mode == "local_only" and provider.get("is_cloud", True):
        return False
    return True


def list_available_models(task_type, privacy_mode="normal"):
    available = []
    chain = build_fallback_chain(task_type)
    for model_name in chain:
        if is_available(model_name, privacy_mode):
            available.append(model_name)
    return available
