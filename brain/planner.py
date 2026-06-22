"""Agentic multi-step planner.

Breaks a complex request into simple step-commands, executes each through the
normal dispatcher, and returns a combined summary.
"""

import json
import os
import re


def plan(text: str) -> list:
    """Return a list of simple step-commands for a complex request."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return [text]  # no planner available — run the request as a single step

    model = os.getenv("GROQ_INTENT_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    system = (
        "Break the user's request into 1 to 5 simple, ordered steps. "
        "Each step must be a short imperative command the assistant can run, "
        "e.g. 'open chrome', 'search python tutorials', 'create folder demo'. "
        "Return ONLY a JSON array of strings, nothing else."
    )
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.2,
                "max_tokens": 200,
            },
            timeout=8,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            steps = json.loads(match.group())
            steps = [str(s).strip() for s in steps if str(s).strip()]
            if steps:
                return steps[:5]
    except Exception as e:
        print(f"[PLANNER] failed reason={type(e).__name__}", flush=True)
    return [text]


def run_plan(text: str) -> str:
    """Plan a request, execute each step, return a combined summary."""
    steps = plan(text)
    from core.dispatcher import _dispatch
    from core.ui_state import emit_state

    if len(steps) == 1:
        return _dispatch(steps[0], "planner", _depth=1)

    results = []
    for i, step in enumerate(steps, 1):
        emit_state("thinking", source="planner", text=step[:80])
        try:
            r = _dispatch(step, "planner", _depth=1)
        except Exception as e:
            r = f"failed ({type(e).__name__})"
        results.append(f"{i}. {step} — {r}")

    return "Here's what I did:\n" + "\n".join(results)
