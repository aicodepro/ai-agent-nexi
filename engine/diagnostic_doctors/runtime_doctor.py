import sys
import os
import importlib
import subprocess
import threading
from datetime import datetime

CHECK_RESULTS = []
_CHECK_RESULTS_LOCK = threading.RLock()

def _check(name, condition, problem="", cause="", fix="", command="", **extra):
    result = {
        "name": name,
        "ok": bool(condition),
        "problem": problem,
        "cause": cause,
        "fix": fix,
        "command": command,
    }
    result.update(extra)
    with _CHECK_RESULTS_LOCK:
        CHECK_RESULTS.append(result)
    return result

def run_all_checks():
    with _CHECK_RESULTS_LOCK:
        CHECK_RESULTS.clear()
        _check_bridge()
        _check_hotword()
        _check_playwright()
        _check_dependencies()
        _check_server_health()
        _check_last_errors()
        _check_emergency_stop()
        _check_model_router()
        _check_memory_storage()
        _check_provider_registry()
        _check_autonomy_loop()
        _check_permission_manager()
        _check_vision_module()
        _check_all_phase3_modules()
        _check_capability_diagnostics()
        return [result.copy() for result in CHECK_RESULTS]


def _run_single_check(checker, expected_name):
    with _CHECK_RESULTS_LOCK:
        previous = list(CHECK_RESULTS)
        CHECK_RESULTS.clear()
        try:
            checker()
            for result in CHECK_RESULTS:
                if result["name"] == expected_name:
                    return result.copy()
        finally:
            CHECK_RESULTS[:] = previous
    return {"name": expected_name, "ok": False, "problem": "Check not found"}

def _check_bridge():
    try:
        from engine.control import execute_control_action, EmergencyStop
        _check("Bridge", True, "", "", "", "")
    except ImportError as e:
        _check("Bridge", False,
               "Control bridge not importable",
               f"Import error: {e}",
               "Verify engine/control/__init__.py exists and has no syntax errors",
               "python -c \"from engine.control import execute_control_action\"")

def _check_hotword():
    try:
        import speech_recognition
        _check("Hotword/Speech", True, "", "", "", "")
    except ImportError:
        _check("Hotword/Speech", False,
               "speech_recognition not installed",
               "Missing package",
               "Install speech_recognition",
               "pip install SpeechRecognition")

def _check_playwright():
    try:
        from playwright.sync_api import sync_playwright
        _check("Playwright", True, "", "", "", "")
    except ImportError:
        _check("Playwright", False,
               "Playwright not installed",
               "Missing package",
               "Install playwright",
               "pip install playwright && playwright install")

def _check_dependencies():
    required = ["psutil", "eel"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        _check("Dependencies", False,
               f"Missing packages: {', '.join(missing)}",
               "Required packages not installed",
               f"Install missing packages",
               f"pip install {' '.join(missing)}")
    else:
        _check("Dependencies", True, "", "", "", "")

def _check_server_health():
    _check("Server Health", False,
           "Server health is unknown",
           "No server health probe is configured",
           "Configure a health probe before reporting server readiness",
           "",
           status="unknown")

def _check_last_errors():
    errors = RuntimeDoctor.get_last_errors(limit=1)
    if errors:
        latest = errors[-1]
        _check("Last Errors", False,
               "Runtime errors have been recorded",
               f"{latest.get('context', '')}: {latest.get('message', '')}".strip(": "),
               "Review the recorded error and its context",
               "",
               status="error")
        return
    _check("Last Errors", True, "", "", "", "", status="clear")

def _check_emergency_stop():
    try:
        from engine.control.safety import EmergencyStop
        _check("Emergency Stop", True, "", "", "", "")
    except ImportError as e:
        _check("Emergency Stop", False,
               "EmergencyStop module not importable",
               f"Import error: {e}",
               "Verify engine/control/safety.py exists",
               "python -c \"from engine.control.safety import EmergencyStop\"")

def _check_model_router():
    try:
        from engine.brain.model_router import route
        if not callable(route):
            raise ImportError("model router route() is not callable")
        _check("Model Router", True, "", "", "", "")
    except ImportError as e:
        _check("Model Router", False,
               "Model Router module not importable",
               f"Import error: {e}",
               "Verify engine/brain/model_router.py exists",
               "python -c \"from engine.brain.model_router import route\"")

def _check_memory_storage():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    mem_dir = os.path.join(root, "data", "memory")
    if not os.path.exists(mem_dir):
        _check("Memory Storage", False,
               "data/memory/ directory not found",
               "First run or directory deleted",
               "Create data/memory/ directory",
               f"mkdir -p \"{mem_dir}\"")
        return
    _check("Memory Storage", True, "", "", "", "")

def _check_provider_registry():
    try:
        from engine.brain.provider_registry import ProviderRegistry
        _check("Provider Registry", True, "", "", "", "")
    except ImportError as e:
        _check("Provider Registry", False,
               "Provider Registry module not importable",
               f"Import error: {e}",
               "Verify engine/brain/provider_registry.py exists",
               "python -c \"from engine.brain.provider_registry import ProviderRegistry\"")

def _check_autonomy_loop():
    try:
        from engine.brain.autonomy_loop import AutonomyLoop
        _check("Autonomy Loop", True, "", "", "", "")
    except ImportError as e:
        _check("Autonomy Loop", False,
               "Autonomy Loop module not importable",
               f"Import error: {e}",
               "Verify engine/brain/autonomy_loop.py exists",
               "python -c \"from engine.brain.autonomy_loop import AutonomyLoop\"")

def _check_permission_manager():
    try:
        from engine.control.permission_manager import PermissionManager
        if callable(getattr(PermissionManager, "evaluate", None)):
            _check("Permission Manager", True, "", "", "", "")
        else:
            _check("Permission Manager", False,
                   "Permission Manager evaluate method is unavailable",
                   "PermissionManager.evaluate is not callable",
                   "Restore PermissionManager.evaluate",
                   "")
    except ImportError as e:
        _check("Permission Manager", False,
               "Permission Manager module not importable",
               f"Import error: {e}",
               "Verify engine/control/permission_manager.py exists",
               "python -c \"from engine.control.permission_manager import PermissionManager\"")

def _check_vision_module():
    try:
        from vision import ScreenObserver
        _check("Vision Module", True, "", "", "", "")
    except ImportError as e:
        _check("Vision Module", False,
               "Vision module not importable",
               f"Import error: {e}",
               "Verify vision/__init__.py exists",
               "python -c \"from vision import ScreenObserver\"")

def _check_all_phase3_modules():
    modules = [
        "engine.brain.task_state",
        "engine.brain.self_reflection",
        "engine.brain.recovery_planner",
        "engine.brain.model_client",
        "engine.brain.provider_factory",
        "engine.memory.memory_policy",
        "engine.memory.memory_redaction",
        "engine.memory.local_memory",
        "engine.memory.preference_store",
        "engine.memory.task_memory",
        "engine.control.permission_manager",
    ]
    failed = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except ImportError:
            failed.append(mod)
    if not failed:
        _check("All Phase 3 Modules", True, "", "", "", "")
    else:
        _check("All Phase 3 Modules", False,
               f"Phase 3 modules failed: {', '.join(failed)}",
               "Import errors in Phase 3 modules",
               "Check each failed module for syntax/import errors",
               f"python -c \"import {failed[0]}\"")


def _check_capability_diagnostics():
    try:
        from engine.diagnostic_capabilities import check_diagnostic_capabilities

        for item in check_diagnostic_capabilities():
            ok = bool(item.get("ok"))
            _check(
                item.get("name", "Capability"),
                ok,
                "" if ok else f"{item.get('name', 'Capability')} is {item.get('status', 'degraded')}",
                item.get("detail", ""),
                item.get("fix", ""),
                item.get("command", ""),
                capability_key=item.get("key", ""),
                feature_id=item.get("feature_id", 0),
                status=item.get("status", ""),
                detail=item.get("detail", ""),
                role=item.get("role", ""),
                safety_policy=item.get("safety_policy", ""),
                verifier=item.get("verifier", ""),
                memory_rule=item.get("memory_rule", ""),
                diagnostic_output=item.get("diagnostic_output", ""),
            )
    except Exception as e:
        _check("Capability Diagnostics", False,
               "Capability diagnostics not available",
               f"Import error: {e}",
               "Verify engine/diagnostic_capabilities.py exists and imports cleanly",
               "python -c \"from engine.diagnostic_capabilities import check_diagnostic_capabilities\"")


class RuntimeDoctor:
    _last_errors = []

    @classmethod
    def diagnose(cls):
        results = run_all_checks()
        failed = [r for r in results if not r["ok"]]
        passed = [r for r in results if r["ok"]]
        summary = f"{len(passed)} checks passed, {len(failed)} issues found."
        if failed:
            issues = []
            for f in failed:
                issues.append(f"** {f['name']}**: {f['problem']}")
                if f["fix"]:
                    issues.append(f"   Fix: {f['fix']}")
                if f["command"]:
                    issues.append(f"   Command: `{f['command']}`")
            summary += " Issues: " + "; ".join(issues)
        return {
            "ok": len(failed) == 0,
            "summary": summary,
            "checks": results,
            "timestamp": datetime.now().isoformat(),
        }

    @classmethod
    def check_hotword(cls):
        return _run_single_check(_check_hotword, "Hotword/Speech")

    @classmethod
    def check_bridge(cls):
        return _run_single_check(_check_bridge, "Bridge")

    @classmethod
    def check_playwright(cls):
        return _run_single_check(_check_playwright, "Playwright")

    @classmethod
    def check_capability(cls, name_or_key):
        from engine.diagnostic_capabilities import get_diagnostic_capability

        item = get_diagnostic_capability(name_or_key)
        if item is None:
            return {"name": str(name_or_key or "Capability"), "ok": False, "problem": "Check not found"}

        def check():
            ok = bool(item.get("ok"))
            _check(
                item.get("name", "Capability"),
                ok,
                "" if ok else f"{item.get('name', 'Capability')} is {item.get('status', 'degraded')}",
                item.get("detail", ""),
                item.get("fix", ""),
                item.get("command", ""),
                capability_key=item.get("key", ""),
                feature_id=item.get("feature_id", 0),
                status=item.get("status", ""),
                detail=item.get("detail", ""),
                role=item.get("role", ""),
                safety_policy=item.get("safety_policy", ""),
                verifier=item.get("verifier", ""),
                memory_rule=item.get("memory_rule", ""),
                diagnostic_output=item.get("diagnostic_output", ""),
            )

        return _run_single_check(check, item.get("name", "Capability"))

    @classmethod
    def log_error(cls, error_message, context=""):
        cls._last_errors.append({
            "message": str(error_message),
            "context": context,
            "timestamp": datetime.now().isoformat(),
        })
        if len(cls._last_errors) > 50:
            cls._last_errors = cls._last_errors[-50:]

    @classmethod
    def get_last_errors(cls, limit=10):
        return list(cls._last_errors[-limit:])

    @classmethod
    def format_diagnosis(cls, result=None):
        if result is None:
            result = cls.diagnose()
        lines = ["Nexi Diagnostics Report", "=" * 40]
        for check in result.get("checks", []):
            status = "OK" if check["ok"] else "ISSUE"
            lines.append(f"  [{status}] {check['name']}")
            if check.get("role"):
                lines.append(f"         Role: {check['role']}")
            if check.get("safety_policy"):
                lines.append(f"         Safety: {check['safety_policy']}")
            if check.get("verifier"):
                lines.append(f"         Verifier: {check['verifier']}")
            if check.get("memory_rule"):
                lines.append(f"         Memory: {check['memory_rule']}")
            if check.get("diagnostic_output"):
                lines.append(f"         Diagnostic: {check['diagnostic_output']}")
            if not check["ok"] and check.get("problem"):
                lines.append(f"         Problem: {check['problem']}")
                if check.get("fix"):
                    lines.append(f"         Fix: {check['fix']}")
        lines.append("=" * 40)
        lines.append(result.get("summary", ""))
        return "\n".join(lines)
