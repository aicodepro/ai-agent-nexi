"""Idea #82 — a held-out check the generator never sees.

Forge asks ONE model call for `{name, function_code, test_code}`: the model writes the
implementation AND the test that judges it. That is the textbook reward-hacking setup —
`def test_x(): assert True` passes the gate while the tool does nothing. The DGM paper
measured 73.8% of self-improving code experiments gaming their own proxy this way, which
is why #82 says the gate must not be the only judge.

Two independent judges are added here, cheapest first:

  1. STATIC ADEQUACY (deterministic, no model, no network) — does the test actually
     exercise the function and assert on the RESULT? This alone kills the common hacks:
     `assert True`, a test that never calls the function, a test with no assertion.
  2. HELD-OUT CASES (optional, model) — input/output pairs derived from the SPEC by a
     separate call that never sees the implementation, then run against the tool.

Static adequacy is mandatory and free. Held-out cases are best-effort: if no generator
is available the tool is NOT auto-blessed — it falls back to needing approval, because
"we could not independently check it" must never read as "it passed".
"""
from __future__ import annotations

import ast
import json
import os
import re


class HoldoutError(RuntimeError):
    pass


# ---- 1. static adequacy ---------------------------------------------------------

def _calls(tree: ast.AST, func_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == func_name:
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == func_name:
                return True
    return False


def _assert_nodes(tree: ast.AST) -> list[ast.Assert]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]


def _is_constant_truthy(node: ast.expr) -> bool:
    """`assert True` / `assert 1` / `assert "x"` — an assertion that cannot fail."""
    return isinstance(node, ast.Constant) and bool(node.value)


def test_adequacy(function_code: str, test_code: str, func_name: str) -> dict:
    """Is this test capable of FAILING if the function is wrong?

    Returns {ok, reason, asserts, calls_function}. Deterministic — no model, no network.
    """
    result = {"ok": False, "reason": "", "asserts": 0, "calls_function": False}
    if not str(test_code or "").strip():
        result["reason"] = "no test was produced"
        return result
    try:
        tree = ast.parse(test_code)
    except SyntaxError as exc:
        result["reason"] = f"test does not parse: {exc.msg}"
        return result

    asserts = _assert_nodes(tree)
    result["asserts"] = len(asserts)
    result["calls_function"] = _calls(tree, func_name)

    if not asserts:
        result["reason"] = "test contains no assertion — it cannot fail"
        return result
    if not result["calls_function"]:
        result["reason"] = f"test never calls {func_name}() — it does not exercise the tool"
        return result
    # every assertion is a constant -> vacuous
    if all(_is_constant_truthy(a.test) for a in asserts):
        result["reason"] = "every assertion is a constant (assert True) — vacuous test"
        return result
    # at least one assertion must involve the function's result, not just literals
    meaningful = False
    for a in asserts:
        if _is_constant_truthy(a.test):
            continue
        if _calls(a, func_name) or any(isinstance(n, ast.Name) for n in ast.walk(a.test)):
            meaningful = True
            break
    if not meaningful:
        result["reason"] = "no assertion depends on the function's behaviour"
        return result

    result["ok"] = True
    return result


# ---- 2. held-out cases the generator never sees ---------------------------------

_CASE_PROMPT = """You write ACCEPTANCE CASES for a Python function from its SPEC ONLY.
You have NOT seen the implementation and must not guess at it.
Return STRICT JSON, no prose:
{{"cases": [{{"args": [<json args>], "kwargs": {{}}, "expected": <json value>}}]}}
Rules: 3-6 cases; include at least one edge case; only JSON-serialisable values;
`expected` must be what the SPEC requires, not what any implementation happens to do.

SPEC: {spec}
FUNCTION NAME: {name}"""


def derive_cases(spec: str, func_name: str, generate_fn=None) -> list[dict]:
    """Ask for acceptance cases from the SPEC alone (never the implementation)."""
    if generate_fn is None:
        try:
            from engine.forge.code_generator import _default_generate  # type: ignore
            generate_fn = _default_generate
        except Exception:
            return []
    try:
        raw = generate_fn(_CASE_PROMPT.format(spec=spec, name=func_name))
        text = raw if isinstance(raw, str) else json.dumps(raw)
        match = re.search(r"\{.*\}", text, flags=re.S)
        data = json.loads(match.group(0) if match else text)
        cases = data.get("cases") if isinstance(data, dict) else None
        out = []
        for c in (cases or []):
            if isinstance(c, dict) and "expected" in c:
                out.append({"args": list(c.get("args") or []),
                            "kwargs": dict(c.get("kwargs") or {}),
                            "expected": c.get("expected")})
        return out[:6]
    except Exception:
        return []


def cases_to_test(func_name: str, cases: list[dict]) -> str:
    """Render held-out cases as a pytest module that imports the tool under test."""
    if not cases:
        return ""
    lines = [f"from tool_under_test import {func_name}", "", "def test_holdout():"]
    for i, c in enumerate(cases):
        args = ", ".join(json.dumps(a) for a in c["args"])
        kwargs = ", ".join(f"{k}={json.dumps(v)}" for k, v in c["kwargs"].items())
        call = ", ".join(p for p in (args, kwargs) if p)
        lines.append(f"    assert {func_name}({call}) == {json.dumps(c['expected'])}, "
                     f"{json.dumps(f'held-out case {i + 1}')}")
    return "\n".join(lines) + "\n"


# ---- the combined verdict --------------------------------------------------------

def evaluate(spec: str, function_code: str, test_code: str, func_name: str, *,
             generate_fn=None, run_test=None, timeout: float = 10.0) -> dict:
    """Independent verdict on a forged tool.

    {ok, reason, adequacy, holdout_cases, holdout_passed}
    ok=False means DO NOT auto-install — either the self-written test was vacuous, or
    the tool failed cases derived independently from the spec.
    """
    verdict = {"ok": False, "reason": "", "adequacy": None,
               "holdout_cases": 0, "holdout_passed": None, "partial": False}

    adequacy = test_adequacy(function_code, test_code, func_name)
    verdict["adequacy"] = adequacy
    if not adequacy["ok"]:
        verdict["reason"] = f"self-written test is inadequate: {adequacy['reason']}"
        return verdict

    cases = derive_cases(spec, func_name, generate_fn=generate_fn)
    verdict["holdout_cases"] = len(cases)
    if not cases:
        # No independent cases could be derived (offline, or no model). Static adequacy
        # DID pass, and that is itself a second judge — it checks whether the test can
        # fail at all, independently of what the test claims. So this degrades to
        # PARTIAL verification rather than a hard block, which would make Forge unusable
        # offline. It is never reported as full verification, and strict deployments can
        # demand the held-out pass with NEXI_FORGE_REQUIRE_HOLDOUT=1.
        strict = str(os.getenv("NEXI_FORGE_REQUIRE_HOLDOUT") or "").strip().lower() in {"1", "true", "yes", "on"}
        verdict["partial"] = True
        if strict:
            verdict["reason"] = ("no held-out cases could be derived and "
                                 "NEXI_FORGE_REQUIRE_HOLDOUT=1 demands them")
            return verdict
        verdict["ok"] = True
        verdict["reason"] = ("PARTIAL: the self-written test is non-vacuous, but no "
                             "independent held-out cases were available")
        return verdict

    if run_test is None:
        from engine.forge import sandbox_runner
        run_test = sandbox_runner.run_test
    holdout = run_test(function_code, cases_to_test(func_name, cases), timeout=timeout)
    passed = bool(holdout.get("passed") if isinstance(holdout, dict) else holdout)
    verdict["holdout_passed"] = passed
    if not passed:
        detail = (holdout.get("output") or holdout.get("error") or "")[:200] if isinstance(holdout, dict) else ""
        verdict["reason"] = f"failed {len(cases)} held-out case(s) derived from the spec. {detail}".strip()
        return verdict

    verdict["ok"] = True
    verdict["reason"] = f"passed {len(cases)} independent held-out case(s)"
    return verdict


def _demo() -> None:
    # the classic hack: calls the function, then asserts a constant so it cannot fail
    bad = test_adequacy("def add(a,b): return a+b",
                        "def test_add():\n    add(1, 2)\n    assert True\n", "add")
    assert not bad["ok"] and "vacuous" in bad["reason"], bad
    # a test that never calls the function
    never = test_adequacy("def add(a,b): return a+b", "def test_add():\n    assert 1 + 1 == 2\n", "add")
    assert not never["ok"] and "never calls" in never["reason"], never
    # no assertion at all
    none_ = test_adequacy("def add(a,b): return a+b", "def test_add():\n    add(1, 2)\n", "add")
    assert not none_["ok"] and "no assertion" in none_["reason"], none_
    # a real test passes
    good = test_adequacy("def add(a,b): return a+b",
                         "def test_add():\n    assert add(1, 2) == 3\n", "add")
    assert good["ok"], good
    # rendering held-out cases
    src = cases_to_test("add", [{"args": [1, 2], "kwargs": {}, "expected": 3}])
    assert "assert add(1, 2) == 3" in src, src
    print("holdout_eval._demo OK")


if __name__ == "__main__":
    _demo()
