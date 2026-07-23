from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor, run_all_checks

diagnose = RuntimeDoctor.diagnose
check_hotword = RuntimeDoctor.check_hotword
check_bridge = RuntimeDoctor.check_bridge
check_playwright = RuntimeDoctor.check_playwright
check_capability = RuntimeDoctor.check_capability
format_diagnosis = RuntimeDoctor.format_diagnosis
