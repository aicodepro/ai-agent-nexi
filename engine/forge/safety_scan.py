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

# Builtins that read/write files, run code, or take stdin — always risky.
DANGEROUS_CALLS = {"eval", "exec", "compile", "open", "__import__", "input", "breakpoint"}


def scan(code: str) -> dict:
    """Classify `code`. Returns {safe: bool, flags: [str], reason: str}."""
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

    flags = sorted(set(flags))
    safe = not flags
    return {"safe": safe, "flags": flags, "reason": "pure compute" if safe else "; ".join(flags)}
