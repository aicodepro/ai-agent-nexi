"""Static safety classification of generated tool code (AST-based).

Conservative: pure-compute code (stdlib math/json/re/etc., no I/O) = safe. Anything
that could touch the filesystem, network, subprocess, or dynamically execute code
= risky (needs approval before it can run outside the sandbox). This runs BEFORE
any execution.
"""
import ast

# Stdlib modules considered pure-compute / safe to import in a forged tool.
SAFE_MODULES = {
    "math", "cmath", "json", "re", "datetime", "time", "string", "collections",
    "itertools", "functools", "statistics", "decimal", "fractions", "random",
    "typing", "dataclasses", "enum", "textwrap", "unicodedata", "base64",
    "hashlib", "uuid", "operator", "heapq", "bisect", "copy", "calendar",
    "numbers", "array",
}

# Builtins that read/write files, run code, take stdin, or defeat the static scan
# by reaching objects/modules reflectively — always risky.
# NOTE: getattr/setattr/vars/globals/locals/__import__ are here because they are the
# standard way to bypass an AST allowlist (e.g. getattr(__builtins__,'__import__')).
DANGEROUS_CALLS = {
    "eval", "exec", "compile", "open", "__import__", "input", "breakpoint",
    "getattr", "setattr", "delattr", "vars", "globals", "locals", "memoryview",
}

# An AST allowlist can NEVER be fully sound (this is why forged tools that touch the
# system need human approval, not just a green scan). But pure-compute code has no
# legitimate reason to touch ANY dunder, so referencing one is a hard risk signal —
# it catches the whole __class__/__subclasses__/__mro__/__globals__/__builtins__
# sandbox-escape family in one rule.
def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def scan(code: str) -> dict:
    """Classify `code`. Returns {safe: bool, flags: [str], reason: str}.

    A `safe` result only means "no obvious system access" — it is NOT proof the code
    is harmless. forge_engine gates on this BEFORE executing, so flagged code is never
    run in the (non-container) sandbox; anything unflagged still runs there.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"safe": False, "flags": ["syntax_error"], "reason": f"syntax error: {exc}"}

    flags: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in SAFE_MODULES:
                    flags.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top not in SAFE_MODULES:
                flags.append(f"from:{node.module}")
        elif isinstance(node, ast.Call):
            fn = node.func
            fname = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if fname in DANGEROUS_CALLS:
                flags.append(f"call:{fname}")
        elif isinstance(node, ast.Attribute):
            if _is_dunder(node.attr):
                flags.append(f"dunder:{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in DANGEROUS_CALLS or _is_dunder(node.id):
                flags.append(f"name:{node.id}")

    flags = sorted(set(flags))
    safe = not flags
    return {"safe": safe, "flags": flags, "reason": "pure compute" if safe else "; ".join(flags)}
