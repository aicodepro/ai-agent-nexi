from src.orin.brain.model_client import (
    ModelClient, MockModelClient, BlockedModelClient,
    make_success_response, make_error_response, validate_request,
)
from src.orin.brain.provider_registry import ProviderRegistry


def _is_blocked_by_privacy(provider_config, privacy_mode):
    if privacy_mode == "local_only" and provider_config.get("is_cloud", True):
        return True
    return False


def _get_client_type(provider_name):
    type_map = {
        "mock": "mock",
        "blocked": "blocked",
    }
    return type_map.get(provider_name, "unknown")


def create_client(model_name, privacy_mode="normal", use_mock=False):
    provider = ProviderRegistry.get_provider(model_name)
    if provider is None:
        return BlockedModelClient(
            model_name=model_name,
            reason=f"Unknown model: {model_name}",
        )
    if not provider.get("enabled", False):
        return BlockedModelClient(
            model_name=model_name,
            reason=f"Provider disabled: {model_name}",
        )
    if _is_blocked_by_privacy(provider, privacy_mode):
        return BlockedModelClient(
            model_name=model_name,
            reason=f"Cloud provider blocked by {privacy_mode} privacy mode",
        )
    if use_mock:
        return MockModelClient(
            model_name=model_name,
            provider_name=provider.get("provider_name", "mock"),
        )
    return MockModelClient(
        model_name=model_name,
        provider_name=provider.get("provider_name", "unknown"),
    )


def create_client_for_decision(route_decision, use_mock=False):
    if not route_decision:
        return BlockedModelClient(
            model_name="",
            reason="No route decision provided",
        )
    selected_model = route_decision.get("selected_model", "")
    if not selected_model:
        return BlockedModelClient(
            model_name="",
            reason="No model selected in route decision",
        )
    privacy_mode = route_decision.get("privacy_mode", "normal")
    return create_client(selected_model, privacy_mode, use_mock=use_mock)


def execute_via_router(task_type, prompt, messages=None,
                       privacy_mode="normal", use_mock=False,
                       max_tokens=0, timeout_seconds=0):
    from src.orin.brain.model_router import route
    decision = route(task_type, privacy_mode=privacy_mode)
    selected_model = decision.get("selected_model", "")
    if not selected_model:
        return make_error_response(
            error_code="NO_MODEL_AVAILABLE",
            error_message=f"No available model for task_type={task_type}, privacy_mode={privacy_mode}",
        )
    client = create_client(selected_model, privacy_mode, use_mock=use_mock)
    request = {
        "model_name": selected_model,
        "task_type": task_type,
        "messages": messages or [],
        "prompt": prompt or "",
        "max_tokens": max_tokens or decision.get("max_tokens", 2048),
        "timeout_seconds": timeout_seconds or decision.get("timeout_seconds", 30),
        "privacy_mode": privacy_mode,
        "allow_cloud": privacy_mode != "local_only",
        "metadata": {},
    }
    return client.generate(request)


def execute_with_client(client, task_type, prompt, messages=None,
                        max_tokens=0, timeout_seconds=0, privacy_mode="normal"):
    request = {
        "model_name": getattr(client, "_model_name", "unknown"),
        "task_type": task_type,
        "messages": messages or [],
        "prompt": prompt or "",
        "max_tokens": max_tokens or 2048,
        "timeout_seconds": timeout_seconds or 30,
        "privacy_mode": privacy_mode,
        "allow_cloud": privacy_mode != "local_only",
        "metadata": {},
    }
    return client.generate(request)
