from engine.brain.model_client import (
    ModelClient, MockModelClient, BlockedModelClient,
    make_success_response, make_error_response, validate_request,
)
from engine.brain.provider_registry import ProviderRegistry
from engine.providers.openai_compat import chat_completion
from engine.providers.base import ProviderResult


class OpenAIModelClient(ModelClient):
    supports_vision = False
    supports_streaming = True
    supports_tools = False
    supports_long_context = False

    def __init__(self, model_name, provider_name, endpoint, api_key,
                 timeout_seconds=30, max_tokens=2048):
        self._model_name = model_name
        self._provider_name = provider_name
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens

    def generate(self, request):
        valid, msg = validate_request(request)
        if not valid:
            return make_error_response(
                model_name=self._model_name,
                provider_name=self._provider_name,
                error_code="INVALID_REQUEST",
                error_message=msg,
            )
        messages = request.get("messages", [])
        prompt = request.get("prompt", "")
        if prompt and not messages:
            messages = [{"role": "user", "content": prompt}]
        elif prompt and messages:
            messages = messages + [{"role": "user", "content": prompt}]
        timeout = request.get("timeout_seconds", self._timeout) or self._timeout
        max_tokens = request.get("max_tokens", self._max_tokens) or self._max_tokens
        payload_messages = messages if messages else [{"role": "user", "content": prompt or "..."}]
        result = chat_completion(
            base_url=self._endpoint.rstrip("/chat/completions").rstrip("/"),
            api_key=self._api_key,
            model=self._model_name,
            messages=payload_messages,
            provider_name=self._provider_name,
            temperature=0.0,
            max_tokens=max_tokens,
            timeout=float(timeout),
            max_retries=1,
        )
        if result.ok:
            content = result.raw_text or ""
            if result.decision:
                content = str(result.decision)
            elif result.tool_call:
                content = f"tool_call: {result.tool_call['name']}({result.tool_call['arguments']})"
            return make_success_response(
                model_name=self._model_name,
                provider_name=self._provider_name,
                content=content,
                input_tokens=len(payload_messages),
                output_tokens=len(content.split()) if content else 1,
                latency_ms=0,
            )
        return make_error_response(
            model_name=self._model_name,
            provider_name=self._provider_name,
            error_code=result.error_code or "PROVIDER_ERROR",
            error_message=f"Provider returned: {result.error_code}",
        )

    def health_check(self):
        key_preview = (self._api_key[:8] + "...") if len(self._api_key) > 8 else "set" if self._api_key else "missing"
        return {
            "ok": bool(self._api_key),
            "model": self._model_name,
            "provider": self._provider_name,
            "endpoint": self._endpoint,
            "api_key": key_preview,
            "reason": "API key set" if self._api_key else "No API key configured",
        }


def _is_blocked_by_privacy(provider_config, privacy_mode):
    if privacy_mode == "local_only" and provider_config.get("is_cloud", True):
        return True
    return False


def _get_client_type(provider_name):
    type_map = {
        "mock": "mock",
        "blocked": "blocked",
    }
    return type_map.get(provider_name, "openai_compat")


def create_client(model_name, privacy_mode="normal", use_mock=False):
    if use_mock:
        return MockModelClient(
            model_name=model_name,
            provider_name="mock",
        )
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
    api_key = ProviderRegistry.resolve_api_key(model_name)
    if not api_key:
        # Known + enabled + privacy-allowed provider with no credentials degrades
        # to a mock so the pipeline stays exercisable offline. Unknown/disabled/
        # privacy-blocked models still return BlockedModelClient. Logged loudly
        # so a missing key in production is never silent.
        print(
            f"[PROVIDER] no API key for {model_name} "
            f"(env: {provider.get('api_key_env', '?')}) - using MockModelClient",
            flush=True,
        )
        return MockModelClient(
            model_name=model_name,
            provider_name=provider.get("provider_name", "mock"),
        )
    endpoint = provider.get("endpoint", "")
    timeout = provider.get("timeout_seconds", 30)
    max_tokens = provider.get("max_tokens", 2048)
    return OpenAIModelClient(
        model_name=model_name,
        provider_name=provider.get("provider_name", "unknown"),
        endpoint=endpoint,
        api_key=api_key,
        timeout_seconds=timeout,
        max_tokens=max_tokens,
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
    from engine.brain.model_router import route
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
