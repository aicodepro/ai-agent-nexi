"""Model-agnostic code generation for the forge.

`generate(spec, generate_fn=None)` asks an LLM to produce a tool function and a
pytest test for it, and returns them parsed. `generate_fn(prompt) -> str` is
injectable — default routes to Nexi's brain; tests pass a fake for determinism.
"""
import json
import re

from engine.forge.tool_installer import sanitize_name


class CodeGenerationError(RuntimeError):
    pass

_PROMPT = """You are Nexi's tool forge. Write ONE self-contained Python function that fulfills the request, plus a pytest test that verifies it.

Request: {spec}

Rules:
- The function module will be saved as forged_tool.py.
- The test must `from forged_tool import <name>` and assert the behavior.
- Use ONLY the Python standard library. Do NOT read/write files, use the network, or spawn subprocesses.

Return STRICT JSON only, no prose:
{{"name": "<snake_case_function_name>", "function_code": "<full module source defining the function>", "test_code": "<pytest test source>"}}"""


def _default_generate(prompt: str) -> str:
    """Ask a JSON-capable model for the tool source.

    NOT the Gemini chat brain: that is a conversational assistant which injects
    persona + memory context and answers in prose, so every forge attempt died on
    JSONDecodeError and no tool was ever installed. Use the intent provider in
    strict-JSON mode instead, on a model the registry knows actually supports
    response_format=json_object (gpt-oss rejects it — see engine/model_registry.py).
    Fails explicitly if no structured provider is available; the conversational
    Gemini brain is not a valid JSON fallback.
    """
    try:
        from engine.model_registry import select_model
        from engine.providers import get_intent_provider
    except Exception as exc:
        raise CodeGenerationError(
            f"Could not initialize the structured code provider: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        provider = get_intent_provider()
        if provider is None or not provider.is_available():
            raise CodeGenerationError("No JSON-capable intent provider is configured for code generation.")
        result = provider.route_with_schema(
            [
                {"role": "system", "content": "You are a code generator. Return strict JSON only, no prose, no markdown."},
                {"role": "user", "content": prompt},
            ],
            {"type": "object"},
            model=select_model("intent_json"),
            timeout=60.0,
        )
        if result.ok and result.raw_text:
            return str(result.raw_text)
        if result.ok and result.decision is not None:
            return json.dumps(result.decision)
        detail = getattr(result, "error", None) or getattr(result, "message", None) or "provider returned no structured output"
        raise CodeGenerationError(f"Structured code provider failed: {detail}")
    except CodeGenerationError:
        raise
    except Exception as exc:
        raise CodeGenerationError(
            f"JSON provider request failed: {type(exc).__name__}: {exc}"
        ) from exc


def generate(spec: str, generate_fn=None) -> dict:
    """Return {name, function_code, test_code}. Raises on unparseable output."""
    gen = generate_fn or _default_generate
    raw = gen(_PROMPT.format(spec=spec))
    match = re.search(r"\{.*\}", str(raw or ""), flags=re.S)
    try:
        data = json.loads(match.group(0) if match else str(raw))
    except (json.JSONDecodeError, TypeError) as exc:
        raise CodeGenerationError(f"Code provider returned invalid JSON: {exc}") from exc
    return {
        "name": sanitize_name(str(data.get("name", "")).strip()),
        "function_code": str(data.get("function_code", "")),
        "test_code": str(data.get("test_code", "")),
    }
