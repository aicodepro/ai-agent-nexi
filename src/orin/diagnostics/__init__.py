from src.orin.diagnostics.runtime_doctor import RuntimeDoctor, run_all_checks

diagnose = RuntimeDoctor.diagnose
check_hotword = RuntimeDoctor.check_hotword
check_bridge = RuntimeDoctor.check_bridge
check_playwright = RuntimeDoctor.check_playwright
format_diagnosis = RuntimeDoctor.format_diagnosis
