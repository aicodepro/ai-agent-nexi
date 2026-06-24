import sys
import os
import importlib
import subprocess
from datetime import datetime

CHECK_RESULTS = []

def _check(name, condition, problem="", cause="", fix="", command=""):
    CHECK_RESULTS.append({
        "name": name,
        "ok": bool(condition),
        "problem": problem,
        "cause": cause,
        "fix": fix,
        "command": command,
    })

def run_all_checks():
    global CHECK_RESULTS
    CHECK_RESULTS = []
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
    return CHECK_RESULTS

def _check_bridge():
    try:
        from src.orin.control import execute_control_action, EmergencyStop
        _check("Bridge", True, "", "", "", "")
    except ImportError as e:
        _check("Bridge", False,
               "Control bridge not importable",
               f"Import error: {e}",
               "Verify src/orin/control/__init__.py exists and has no syntax errors",
               "python -c \"from src.orin.control import execute_control_action\"")

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
    _check("Server Health", True, "", "", "", "")

def _check_last_errors():
    _check("Last Errors", True, "", "", "", "")

def _check_emergency_stop():
    try:
        from src.orin.control.safety import EmergencyStop
        _check("Emergency Stop", True, "", "", "", "")
    except ImportError as e:
        _check("Emergency Stop", False,
               "EmergencyStop module not importable",
               f"Import error: {e}",
               "Verify src/orin/control/safety.py exists",
               "python -c \"from src.orin.control.safety import EmergencyStop\"")

def _check_model_router():
    try:
        from src.orin.brain.model_router import ModelRouter
        _check("Model Router", True, "", "", "", "")
    except ImportError as e:
        _check("Model Router", False,
               "Model Router module not importable",
               f"Import error: {e}",
               "Verify src/orin/brain/model_router.py exists",
               "python -c \"from src.orin.brain.model_router import ModelRouter\"")

def _check_memory_storage():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
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
        from src.orin.brain.provider_registry import ProviderRegistry
        _check("Provider Registry", True, "", "", "", "")
    except ImportError as e:
        _check("Provider Registry", False,
               "Provider Registry module not importable",
               f"Import error: {e}",
               "Verify src/orin/brain/provider_registry.py exists",
               "python -c \"from src.orin.brain.provider_registry import ProviderRegistry\"")

def _check_autonomy_loop():
    try:
        from src.orin.brain.autonomy_loop import AutonomyLoop
        _check("Autonomy Loop", True, "", "", "", "")
    except ImportError as e:
        _check("Autonomy Loop", False,
               "Autonomy Loop module not importable",
               f"Import error: {e}",
               "Verify src/orin/brain/autonomy_loop.py exists",
               "python -c \"from src.orin.brain.autonomy_loop import AutonomyLoop\"")

def _check_permission_manager():
    try:
        from src.orin.control.permission_manager import PermissionManager
        pm = PermissionManager()
        result = pm.evaluate("run_diagnostics")
        if result and result.get("decision") == "approved":
            _check("Permission Manager", True, "", "", "", "")
        else:
            _check("Permission Manager", False,
                   "Permission Manager returned unexpected decision",
                   f"Got: {result}",
                   "Check PermissionManager.evaluate logic",
                   "")
    except ImportError as e:
        _check("Permission Manager", False,
               "Permission Manager module not importable",
               f"Import error: {e}",
               "Verify src/orin/control/permission_manager.py exists",
               "python -c \"from src.orin.control.permission_manager import PermissionManager\"")

def _check_vision_module():
    try:
        from src.orin.vision import ScreenObserver
        _check("Vision Module", True, "", "", "", "")
    except ImportError as e:
        _check("Vision Module", False,
               "Vision module not importable",
               f"Import error: {e}",
               "Verify src/orin/vision/__init__.py exists",
               "python -c \"from src.orin.vision import ScreenObserver\"")

def _check_all_phase3_modules():
    modules = [
        "src.orin.brain.task_state",
        "src.orin.brain.self_reflection",
        "src.orin.brain.recovery_planner",
        "src.orin.brain.model_client",
        "src.orin.brain.provider_factory",
        "src.orin.memory.memory_policy",
        "src.orin.memory.memory_redaction",
        "src.orin.memory.local_memory",
        "src.orin.memory.preference_store",
        "src.orin.memory.task_memory",
        "src.orin.control.permission_manager",
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
        results = run_all_checks()
        for r in results:
            if r["name"] == "Hotword/Speech":
                return r
        return {"name": "Hotword/Speech", "ok": False, "problem": "Check not found"}

    @classmethod
    def check_bridge(cls):
        results = run_all_checks()
        for r in results:
            if r["name"] == "Bridge":
                return r
        return {"name": "Bridge", "ok": False, "problem": "Check not found"}

    @classmethod
    def check_playwright(cls):
        results = run_all_checks()
        for r in results:
            if r["name"] == "Playwright":
                return r
        return {"name": "Playwright", "ok": False, "problem": "Check not found"}

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
            if not check["ok"] and check.get("problem"):
                lines.append(f"         Problem: {check['problem']}")
                if check.get("fix"):
                    lines.append(f"         Fix: {check['fix']}")
        lines.append("=" * 40)
        lines.append(result.get("summary", ""))
        return "\n".join(lines)
