"""Model-agnostic code generation for the forge.

`generate(spec, generate_fn=None)` asks an LLM to produce a tool function and a
pytest test for it, and returns them parsed. `generate_fn(prompt) -> str` is
injectable — default routes to Nexi's brain; tests pass a fake for determinism.
"""
import json
import re

_PROMPT = """You are Nexi's tool forge. Write ONE self-contained Python function that fulfills the request, plus a pytest test that verifies it.

Request: {spec}

Rules:
- The function module will be saved as forged_tool.py.
- The test must `from forged_tool import <name>` and assert the behavior.
- Use ONLY the Python standard library. Do NOT read/write files, use the network, or spawn subprocesses.

Return STRICT JSON only, no prose:
{{"name": "<snake_case_function_name>", "function_code": "<full module source defining the function>", "test_code": "<pytest test source>"}}"""


def _default_generate(prompt: str) -> str:
    from engine.gemini_brain import ask_gemini  # lazy: heavy import
    return str(ask_gemini(prompt) or "")


def generate(spec: str, generate_fn=None) -> dict:
    """Return {name, function_code, test_code}. Raises on unparseable output."""
    gen = generate_fn or _default_generate
    raw = gen(_PROMPT.format(spec=spec))
    match = re.search(r"\{.*\}", str(raw or ""), flags=re.S)
    data = json.loads(match.group(0) if match else str(raw))
    return {
        "name": str(data.get("name", "")).strip(),
        "function_code": str(data.get("function_code", "")),
        "test_code": str(data.get("test_code", "")),
    }
