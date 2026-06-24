import time
from src.orin.brain.model_policy import get_policy, is_valid_task_type, get_default_policy
from src.orin.brain.provider_registry import ProviderRegistry
from src.orin.brain.model_fallback import is_available
from src.orin.brain.model_metrics import ModelMetrics


PRIVACY_MODES = ("normal", "private", "local_only")

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_TOKENS = 2048


def _select_model(task_type, privacy_mode):
    policy = get_policy(task_type)
    if policy is None:
        policy = get_default_policy()
        task_type = "fast_intent"
    preferred = policy["preferred"]
    fallback = policy["fallback"]
    if is_available(preferred, privacy_mode):
        return preferred, fallback, False
    if is_available(fallback, privacy_mode):
        return fallback, fallback, True
    chain = [
        "deepseek_v4_pro", "deepseek_r1", "deepseek_v3_2",
        "glm_5_1", "kimi_2_6", "minimax_2_7", "qwen3",
    ]
    for model_name in chain:
        if is_available(model_name, privacy_mode):
            return model_name, fallback, model_name != preferred
    return "", fallback, False


def route(task_type, privacy_mode="normal"):
    start = time.time()
    if not is_valid_task_type(task_type):
        task_type = "fast_intent"
    if privacy_mode not in PRIVACY_MODES:
        privacy_mode = "normal"
    policy = get_policy(task_type)
    if policy is None:
        policy = get_default_policy()
    preferred = policy["preferred"]
    fallback = policy["fallback"]
    selected_model, fallback_used = preferred, False
    if not is_available(preferred, privacy_mode):
        selected_model, fallback_used = _try_fallback(policy, privacy_mode)
    timeout = policy.get("timeout_seconds", DEFAULT_TIMEOUT)
    max_tokens = policy.get("max_tokens", DEFAULT_MAX_TOKENS)
    provider = ProviderRegistry.get_provider(selected_model)
    allow_cloud = privacy_mode != "local_only"
    reason = _build_reason(selected_model, preferred, privacy_mode)
    decision = {
        "task_type": task_type,
        "preferred_model": preferred,
        "fallback_model": fallback,
        "selected_model": selected_model,
        "reason": reason,
        "timeout_seconds": timeout,
        "max_tokens": max_tokens,
        "privacy_mode": privacy_mode,
        "allow_cloud": allow_cloud,
        "fallback_used": fallback_used,
    }
    duration = int((time.time() - start) * 1000)
    ModelMetrics.record_decision(decision, duration)
    return decision


def _try_fallback(policy, privacy_mode):
    fallback = policy["fallback"]
    if is_available(fallback, privacy_mode):
        return fallback, True
    chain = [
        "deepseek_v4_pro", "deepseek_r1", "deepseek_v3_2",
        "glm_5_1", "kimi_2_6", "minimax_2_7", "qwen3",
    ]
    for model_name in chain:
        if model_name != policy["preferred"] and is_available(model_name, privacy_mode):
            return model_name, model_name != policy["preferred"]
    return "", True


def _build_reason(selected, preferred, privacy_mode):
    if not selected:
        return "No model available for this task type and privacy mode"
    if selected == preferred:
        return f"Preferred model {preferred} selected"
    if privacy_mode == "local_only":
        return f"Preferred {preferred} is cloud; fell back to {selected}"
    return f"Preferred {preferred} unavailable; fell back to {selected}"


def route_batch(task_types, privacy_mode="normal"):
    return [route(tt, privacy_mode) for tt in task_types]


def is_model_eligible(model_name, task_type, privacy_mode="normal"):
    policy = get_policy(task_type)
    if policy is None:
        return False
    if not is_available(model_name, privacy_mode):
        return False
    return model_name == policy["preferred"] or model_name == policy["fallback"]


def check_connectivity(model_name):
    provider = ProviderRegistry.get_provider(model_name)
    if provider is None:
        return {"model": model_name, "available": False, "reason": "Unknown model"}
    if not provider.get("enabled", False):
        return {"model": model_name, "available": False, "reason": "Provider disabled"}
    has_env = bool(provider.get("api_key_env", ""))
    return {
        "model": model_name,
        "available": has_env,
        "reason": "API key env var set" if has_env else "API key env var not set",
    }
