from src.orin.diagnostics.runtime_doctor import RuntimeDoctor, _check, run_all_checks, CHECK_RESULTS


class BridgeDoctor:
    @classmethod
    def check(cls):
        results = run_all_checks()
        for r in results:
            if r["name"] == "Bridge":
                return r
        return {"name": "Bridge", "ok": False, "problem": "Bridge check not available"}

    @classmethod
    def is_control_available(cls):
        try:
            from src.orin.control import execute_control_action
            return True
        except ImportError:
            return False
