import time
import threading


SUPPORTED_FEATURES = ("vision", "streaming", "tools", "long_context")


def make_request(model_name="", task_type="", prompt="", messages=None,
                 max_tokens=0, timeout_seconds=0, privacy_mode="normal",
                 allow_cloud=True, metadata=None):
    return {
        "model_name": model_name,
        "task_type": task_type,
        "messages": messages or [],
        "prompt": prompt,
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
        "privacy_mode": privacy_mode,
        "allow_cloud": allow_cloud,
        "metadata": metadata or {},
    }


def make_success_response(model_name="", provider_name="", content="",
                          input_tokens=0, output_tokens=0, latency_ms=0):
    return {
        "ok": True,
        "model_name": model_name,
        "provider_name": provider_name,
        "content": content,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "latency_ms": latency_ms,
        "error": None,
    }


def make_error_response(model_name="", provider_name="", error_code="",
                        error_message="", latency_ms=0):
    return {
        "ok": False,
        "model_name": model_name,
        "provider_name": provider_name,
        "content": "",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
        },
        "latency_ms": latency_ms,
        "error": {
            "code": error_code,
            "message": error_message,
        },
    }


def validate_request(request):
    required = ("model_name", "task_type", "privacy_mode", "allow_cloud")
    for field in required:
        if field not in request:
            return False, f"Missing required field: {field}"
    if not isinstance(request.get("messages", []), list):
        return False, "messages must be a list"
    if not isinstance(request.get("allow_cloud"), bool):
        return False, "allow_cloud must be a boolean"
    return True, ""


class ModelClient:
    supports_vision = False
    supports_streaming = False
    supports_tools = False
    supports_long_context = False

    def generate(self, request):
        raise NotImplementedError("generate() must be implemented by subclass")

    def health_check(self):
        raise NotImplementedError("health_check() must be implemented by subclass")

    def get_capabilities(self):
        return {
            "vision": self.supports_vision,
            "streaming": self.supports_streaming,
            "tools": self.supports_tools,
            "long_context": self.supports_long_context,
        }

    def validate_request(self, request):
        return validate_request(request)


class MockModelClient(ModelClient):
    supports_vision = True
    supports_streaming = True
    supports_tools = True
    supports_long_context = True

    def __init__(self, model_name="mock_model", provider_name="mock_provider",
                 simulate_failure=False, simulate_timeout=False,
                 response_delay_ms=0):
        self._model_name = model_name
        self._provider_name = provider_name
        self._simulate_failure = simulate_failure
        self._simulate_timeout = simulate_timeout
        self._response_delay_ms = response_delay_ms
        self._call_count = 0
        self._lock = threading.Lock()

    def generate(self, request):
        with self._lock:
            self._call_count += 1
        valid, msg = validate_request(request)
        if not valid:
            return make_error_response(
                model_name=self._model_name,
                provider_name=self._provider_name,
                error_code="INVALID_REQUEST",
                error_message=msg,
            )
        if self._simulate_timeout:
            return make_error_response(
                model_name=self._model_name,
                provider_name=self._provider_name,
                error_code="TIMEOUT",
                error_message="Request timed out",
            )
        if self._simulate_failure:
            return make_error_response(
                model_name=self._model_name,
                provider_name=self._provider_name,
                error_code="INTERNAL_ERROR",
                error_message="Mock simulated failure",
            )
        if self._response_delay_ms > 0:
            time.sleep(self._response_delay_ms / 1000.0)
        prompt = request.get("prompt", "") or ""
        messages = request.get("messages", [])
        content = f"[Mock] Response to: {prompt or messages}"
        return make_success_response(
            model_name=self._model_name,
            provider_name=self._provider_name,
            content=content,
            input_tokens=len(prompt.split()) if prompt else 10,
            output_tokens=len(content.split()),
            latency_ms=self._response_delay_ms,
        )

    def health_check(self):
        if self._simulate_failure:
            return {"ok": False, "model": self._model_name, "reason": "Simulated failure"}
        return {"ok": True, "model": self._model_name, "reason": "Mock provider healthy"}

    def call_count(self):
        with self._lock:
            return self._call_count


class BlockedModelClient(ModelClient):
    supports_vision = False
    supports_streaming = False
    supports_tools = False
    supports_long_context = False

    def __init__(self, model_name="", reason=""):
        self._model_name = model_name
        self._reason = reason or "Provider blocked by privacy policy"

    def generate(self, request):
        return make_error_response(
            model_name=self._model_name,
            provider_name="",
            error_code="BLOCKED",
            error_message=self._reason,
        )

    def health_check(self):
        return {"ok": False, "model": self._model_name, "reason": self._reason}
