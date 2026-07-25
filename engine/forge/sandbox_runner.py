"""Run a forged tool's test in an isolated subprocess.

Writes the tool module + its test to a throwaway temp dir and runs pytest there
in a separate Python process with a hard timeout, so generated code never runs in
Nexi's main process during validation. Windows console window is suppressed.

Ceiling (ponytail): this is process isolation + timeout, not an OS/container
sandbox. Safe (static-scanned pure-compute) code is fine here; untrusted risky
code would need a container — that's the Phase-2+ upgrade path.
"""
import os
import shutil
import subprocess
import sys
import tempfile

CREATE_NO_WINDOW = 0x08000000


def run_test(function_code: str, test_code: str, timeout: float = 10.0) -> dict:
    """Return {passed: bool, output: str, returncode: int}. The test must import
    the tool via `from forged_tool import <name>`."""
    workdir = tempfile.mkdtemp(prefix="nexi_forge_")
    try:
        with open(os.path.join(workdir, "forged_tool.py"), "w", encoding="utf-8") as fh:
            fh.write(function_code)
        with open(os.path.join(workdir, "test_forged.py"), "w", encoding="utf-8") as fh:
            fh.write(test_code)

        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "test_forged.py", "-q", "-p", "no:cacheprovider"],
                cwd=workdir, capture_output=True, text=True, timeout=timeout, **kwargs
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "output": f"test timed out after {timeout}s", "returncode": -1}
        return {
            "passed": proc.returncode == 0,
            "output": (proc.stdout + proc.stderr)[-2000:],
            "returncode": proc.returncode,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
