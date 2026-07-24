def _stub_all_checks(monkeypatch, runtime):
    names = (
        "_check_bridge",
        "_check_hotword",
        "_check_playwright",
        "_check_dependencies",
        "_check_server_health",
        "_check_last_errors",
        "_check_emergency_stop",
        "_check_model_router",
        "_check_memory_storage",
        "_check_provider_registry",
        "_check_autonomy_loop",
        "_check_permission_manager",
        "_check_vision_module",
        "_check_all_phase3_modules",
        "_check_capability_diagnostics",
    )
    for name in names:
        monkeypatch.setattr(runtime, name, lambda name=name: runtime._check(name, True))


def test_run_all_checks_preserves_and_protects_shared_results(monkeypatch):
    from engine.diagnostic_doctors import runtime_doctor as runtime

    _stub_all_checks(monkeypatch, runtime)
    shared = runtime.CHECK_RESULTS

    results = runtime.run_all_checks()

    assert runtime.CHECK_RESULTS is shared
    assert results is not shared
    before = list(shared)
    results.append({"name": "caller mutation"})
    assert shared == before


def test_runtime_wrapper_runs_only_requested_check(monkeypatch):
    from engine.diagnostic_doctors import runtime_doctor as runtime

    calls = []
    runtime.CHECK_RESULTS[:] = [{"name": "sentinel"}]
    monkeypatch.setattr(
        runtime,
        "_check_hotword",
        lambda: calls.append("hotword") or runtime._check("Hotword/Speech", True),
    )
    monkeypatch.setattr(
        runtime,
        "_check_bridge",
        lambda: (_ for _ in ()).throw(AssertionError("unrequested check ran")),
    )

    result = runtime.RuntimeDoctor.check_hotword()

    assert result["name"] == "Hotword/Speech"
    assert calls == ["hotword"]
    assert runtime.CHECK_RESULTS == [{"name": "sentinel"}]


def test_runtime_bridge_wrapper_runs_only_bridge_check(monkeypatch):
    from engine.diagnostic_doctors import runtime_doctor as runtime

    calls = []
    monkeypatch.setattr(
        runtime,
        "_check_bridge",
        lambda: calls.append("bridge") or runtime._check("Bridge", True),
    )
    monkeypatch.setattr(
        runtime,
        "_check_hotword",
        lambda: (_ for _ in ()).throw(AssertionError("unrequested check ran")),
    )

    result = runtime.RuntimeDoctor.check_bridge()

    assert result["name"] == "Bridge"
    assert calls == ["bridge"]


def test_runtime_playwright_wrapper_runs_only_playwright_check(monkeypatch):
    from engine.diagnostic_doctors import runtime_doctor as runtime

    calls = []
    monkeypatch.setattr(
        runtime,
        "_check_playwright",
        lambda: calls.append("playwright") or runtime._check("Playwright", True),
    )
    monkeypatch.setattr(
        runtime,
        "_check_bridge",
        lambda: (_ for _ in ()).throw(AssertionError("unrequested check ran")),
    )

    result = runtime.RuntimeDoctor.check_playwright()

    assert result["name"] == "Playwright"
    assert calls == ["playwright"]


def test_component_doctors_delegate_to_single_runtime_checks(monkeypatch):
    from engine.diagnostic_doctors import bridge_doctor, hotword_doctor, playwright_doctor

    cases = (
        (bridge_doctor, bridge_doctor.BridgeDoctor, "check_bridge", "Bridge"),
        (hotword_doctor, hotword_doctor.HotwordDoctor, "check_hotword", "Hotword/Speech"),
        (playwright_doctor, playwright_doctor.PlaywrightDoctor, "check_playwright", "Playwright"),
    )
    for module, doctor, method, expected_name in cases:
        fake_runtime = type(
            "FakeRuntime",
            (),
            {method: classmethod(lambda cls, name=expected_name: {"name": name, "ok": True})},
        )
        monkeypatch.setattr(module, "RuntimeDoctor", fake_runtime)
        monkeypatch.setattr(
            module,
            "run_all_checks",
            lambda: (_ for _ in ()).throw(AssertionError("full suite ran")),
            raising=False,
        )

        assert doctor.check()["name"] == expected_name


def test_specific_capability_check_evaluates_only_matching_capability(monkeypatch):
    import engine.diagnostic_capabilities as capabilities

    calls = []

    class Status:
        def __init__(self, spec):
            self.spec = spec

        def to_dict(self):
            return {
                "feature_id": self.spec.feature_id,
                "key": self.spec.key,
                "name": self.spec.name,
            }

    monkeypatch.setattr(
        capabilities,
        "_status_for",
        lambda spec: calls.append(spec.key) or Status(spec),
    )

    result = capabilities.get_diagnostic_capability("tool verifier layer")

    assert result["key"] == "tool_verifier_layer"
    assert calls == ["tool_verifier_layer"]


def test_server_health_is_explicitly_unknown_without_a_probe():
    from engine.diagnostic_doctors import runtime_doctor as runtime

    result = runtime._run_single_check(runtime._check_server_health, "Server Health")

    assert result["ok"] is False
    assert result["status"] == "unknown"


def test_last_errors_reports_recorded_runtime_error():
    from engine.diagnostic_doctors import runtime_doctor as runtime

    runtime.RuntimeDoctor._last_errors = []
    runtime.RuntimeDoctor.log_error("camera failed", context="camera")

    result = runtime._run_single_check(runtime._check_last_errors, "Last Errors")

    assert result["ok"] is False
    assert result["status"] == "error"
    assert "camera failed" in result["cause"]


def test_permission_diagnostic_does_not_evaluate_or_mutate_state(monkeypatch):
    import sys
    import types
    from engine.diagnostic_doctors import runtime_doctor as runtime

    class PermissionManager:
        def __init__(self):
            raise AssertionError("diagnostic instantiated permission manager")

        def evaluate(self, _action):
            raise AssertionError("diagnostic evaluated permission state")

    module = types.ModuleType("engine.control.permission_manager")
    module.PermissionManager = PermissionManager
    monkeypatch.setitem(sys.modules, "engine.control.permission_manager", module)

    result = runtime._run_single_check(runtime._check_permission_manager, "Permission Manager")

    assert result["ok"] is True


def test_runtime_capability_wrapper_does_not_run_full_suite(monkeypatch):
    from engine.diagnostic_doctors import runtime_doctor as runtime

    monkeypatch.setattr(
        runtime,
        "run_all_checks",
        lambda: (_ for _ in ()).throw(AssertionError("full suite ran")),
    )

    result = runtime.RuntimeDoctor.check_capability("tool verifier layer")

    assert result["name"] == "Tool Verifier Layer"
    assert result["capability_key"] == "tool_verifier_layer"
