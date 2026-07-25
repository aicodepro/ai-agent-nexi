import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from engine.brain.model_policy import (
    ROUTING_POLICY, TASK_TYPES, get_policy, is_valid_task_type,
    get_default_policy, list_task_types, list_model_names,
)
from engine.brain.provider_registry import (
    ProviderRegistry, DEFAULT_PROVIDERS, PRIVACY_MODES,
)
from engine.brain.model_fallback import (
    build_fallback_chain, resolve_model, is_available, list_available_models,
)
from engine.brain.model_metrics import ModelMetrics
from engine.brain.model_router import route, route_batch, check_connectivity


class TestModelPolicy(unittest.TestCase):
    def test_routing_policy_has_all_task_types(self):
        for task_type in ("fast_intent", "deep_planning", "coding", "review", "long_context", "experimental"):
            self.assertIn(task_type, ROUTING_POLICY)

    def test_each_policy_has_preferred_and_fallback(self):
        for task_type, policy in ROUTING_POLICY.items():
            self.assertIn("preferred", policy, f"{task_type} missing preferred")
            self.assertIn("fallback", policy, f"{task_type} missing fallback")

    def test_get_policy_returns_correct(self):
        policy = get_policy("coding")
        self.assertEqual(policy["preferred"], "glm_5_1")
        self.assertEqual(policy["fallback"], "kimi_2_6")

    def test_get_policy_nonexistent_returns_none(self):
        self.assertIsNone(get_policy("nonexistent_task"))

    def test_is_valid_task_type(self):
        self.assertTrue(is_valid_task_type("fast_intent"))
        self.assertFalse(is_valid_task_type("invalid_task"))

    def test_get_default_policy_returns_fast_intent(self):
        default = get_default_policy()
        self.assertEqual(default["preferred"], "qwen3")

    def test_list_task_types_returns_all(self):
        types = list_task_types()
        self.assertEqual(len(types), 6)
        self.assertIn("coding", types)

    def test_list_model_names_includes_all(self):
        names = list_model_names()
        self.assertIn("deepseek_v4_pro", names)
        self.assertIn("glm_5_1", names)
        self.assertIn("minimax_2_7", names)


class TestProviderRegistry(unittest.TestCase):
    def setUp(self):
        ProviderRegistry.reset()
        ProviderRegistry.load_defaults()

    def test_default_providers_loaded(self):
        self.assertGreater(ProviderRegistry.count_providers(), 0)

    def test_get_provider_exists(self):
        provider = ProviderRegistry.get_provider("deepseek_v4_pro")
        self.assertIsNotNone(provider)
        self.assertEqual(provider["model_name"], "deepseek_v4_pro")

    def test_get_provider_nonexistent(self):
        provider = ProviderRegistry.get_provider("nonexistent_model")
        self.assertIsNone(provider)

    def test_is_enabled_true(self):
        self.assertTrue(ProviderRegistry.is_enabled("glm_5_1"))

    def test_is_enabled_false_for_disabled(self):
        ProviderRegistry.disable("glm_5_1")
        self.assertFalse(ProviderRegistry.is_enabled("glm_5_1"))

    def test_is_enabled_false_for_unknown(self):
        self.assertFalse(ProviderRegistry.is_enabled("unknown_model"))

    def test_enable_and_disable(self):
        ProviderRegistry.disable("qwen3")
        self.assertFalse(ProviderRegistry.is_enabled("qwen3"))
        ProviderRegistry.enable("qwen3")
        self.assertTrue(ProviderRegistry.is_enabled("qwen3"))

    def test_mimo_disabled_by_default(self):
        self.assertFalse(ProviderRegistry.is_enabled("mimo"))

    def test_is_cloud(self):
        self.assertTrue(ProviderRegistry.is_cloud("deepseek_v4_pro"))
        ProviderRegistry.disable("deepseek_v4_pro")
        self.assertTrue(ProviderRegistry.is_cloud("deepseek_v4_pro"))

    def test_list_enabled_models(self):
        enabled = ProviderRegistry.list_enabled_models()
        self.assertIn("glm_5_1", enabled)
        self.assertNotIn("mimo", enabled)

    def test_get_api_key_env(self):
        env = ProviderRegistry.get_api_key_env("deepseek_v4_pro")
        self.assertEqual(env, "DEEPSEEK_API_KEY")

    def test_get_api_key_env_unknown(self):
        env = ProviderRegistry.get_api_key_env("nonexistent")
        self.assertIsNone(env)

    def test_set_enabled_batch(self):
        ProviderRegistry.set_enabled_batch(
            enabled_list=["deepseek_v4_pro", "glm_5_1"],
            disabled_list=["qwen3"],
        )
        self.assertTrue(ProviderRegistry.is_enabled("deepseek_v4_pro"))
        self.assertTrue(ProviderRegistry.is_enabled("glm_5_1"))
        self.assertFalse(ProviderRegistry.is_enabled("qwen3"))

    def test_provider_config_validates_required_fields(self):
        valid = ProviderRegistry._validate_entry({
            "provider_name": "test",
            "model_name": "test_model",
            "endpoint": "https://api.test.com",
            "api_key_env": "TEST_KEY",
            "enabled": True,
        })
        self.assertTrue(valid)

    def test_provider_config_rejects_missing_fields(self):
        invalid = ProviderRegistry._validate_entry({
            "provider_name": "test",
        })
        self.assertFalse(invalid)

    def test_provider_config_rejects_non_bool_enabled(self):
        invalid = ProviderRegistry._validate_entry({
            "provider_name": "test",
            "model_name": "test_model",
            "endpoint": "https://api.test.com",
            "api_key_env": "TEST_KEY",
            "enabled": "yes",
        })
        self.assertFalse(invalid)


class TestModelFallback(unittest.TestCase):
    def setUp(self):
        ProviderRegistry.reset()
        ProviderRegistry.load_defaults()

    def test_build_fallback_chain_has_preferred_first(self):
        chain = build_fallback_chain("coding")
        self.assertEqual(chain[0], "glm_5_1")

    def test_build_fallback_chain_includes_fallback(self):
        chain = build_fallback_chain("deep_planning")
        self.assertIn("deepseek_r1", chain)

    def test_build_fallback_chain_for_unknown_returns_empty(self):
        chain = build_fallback_chain("nonexistent")
        self.assertEqual(chain, [])

    def test_resolve_model_returns_preferred(self):
        model, reason = resolve_model("coding")
        self.assertEqual(model, "glm_5_1")
        self.assertEqual(reason, "")

    def test_is_available_true_for_enabled_model(self):
        self.assertTrue(is_available("deepseek_v4_pro"))

    def test_is_available_false_for_disabled_model(self):
        ProviderRegistry.disable("deepseek_v4_pro")
        self.assertFalse(is_available("deepseek_v4_pro"))

    def test_is_available_false_for_unknown_model(self):
        self.assertFalse(is_available("nonexistent"))

    def test_local_only_blocks_cloud(self):
        self.assertFalse(is_available("deepseek_v4_pro", privacy_mode="local_only"))

    def test_list_available_models(self):
        available = list_available_models("coding")
        self.assertIn("glm_5_1", available)

    def test_resolve_model_fallback_when_preferred_disabled(self):
        ProviderRegistry.disable("qwen3")
        model, reason = resolve_model("fast_intent")
        self.assertEqual(model, "deepseek_v3_2")

    def test_resolve_model_local_only_returns_none(self):
        model, reason = resolve_model("fast_intent", privacy_mode="local_only")
        self.assertIsNone(model)
        self.assertIn("No available model", reason)


class TestModelMetrics(unittest.TestCase):
    def setUp(self):
        ModelMetrics.clear()

    def test_record_route(self):
        ModelMetrics.record("coding", "glm_5_1", "glm_5_1",
                            fallback_used=False, privacy_mode="normal")
        history = ModelMetrics.get_history()
        self.assertEqual(len(history), 1)

    def test_record_decision(self):
        decision = {
            "task_type": "fast_intent",
            "preferred_model": "qwen3",
            "selected_model": "qwen3",
            "fallback_used": False,
            "privacy_mode": "normal",
            "reason": "Preferred model qwen3 selected",
        }
        ModelMetrics.record_decision(decision, duration_ms=5)
        history = ModelMetrics.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["task_type"], "fast_intent")

    def test_get_summary_empty(self):
        summary = ModelMetrics.get_summary()
        self.assertEqual(summary["total_routes"], 0)

    def test_get_summary_with_routes(self):
        ModelMetrics.record("coding", "glm_5_1", "glm_5_1",
                            fallback_used=False, privacy_mode="normal")
        ModelMetrics.record("fast_intent", "qwen3", "deepseek_v3_2",
                            fallback_used=True, privacy_mode="normal")
        summary = ModelMetrics.get_summary()
        self.assertEqual(summary["total_routes"], 2)
        self.assertGreater(summary["fallback_rate"], 0)

    def test_clear_metrics(self):
        ModelMetrics.record("test", "a", "a", False, "normal")
        ModelMetrics.clear()
        self.assertEqual(len(ModelMetrics.get_history()), 0)

    def test_no_secrets_in_metrics(self):
        decision = {
            "task_type": "coding",
            "preferred_model": "glm_5_1",
            "selected_model": "glm_5_1",
            "fallback_used": False,
            "privacy_mode": "normal",
            "reason": "ok",
        }
        ModelMetrics.record_decision(decision)
        entry = ModelMetrics.get_history()[0]
        self.assertNotIn("api_key", str(entry))
        self.assertNotIn("password", str(entry))
        self.assertNotIn("token", str(entry))
        self.assertNotIn("secret", str(entry))

    def test_disabled_metrics(self):
        ModelMetrics.set_enabled(False)
        ModelMetrics.record("test", "a", "a", False, "normal")
        self.assertEqual(len(ModelMetrics.get_history()), 0)
        ModelMetrics.set_enabled(True)


class TestModelRouter(unittest.TestCase):
    def setUp(self):
        ProviderRegistry.reset()
        ProviderRegistry.load_defaults()
        ModelMetrics.clear()

    def test_fast_intent_routes_to_qwen3(self):
        decision = route("fast_intent")
        self.assertEqual(decision["selected_model"], "qwen3")
        self.assertEqual(decision["preferred_model"], "qwen3")
        self.assertFalse(decision["fallback_used"])

    def test_fast_intent_fallback_when_qwen_disabled(self):
        ProviderRegistry.disable("qwen3")
        decision = route("fast_intent")
        self.assertEqual(decision["selected_model"], "deepseek_v3_2")
        self.assertTrue(decision["fallback_used"])

    def test_deep_planning_routes_to_deepseek_v4_pro(self):
        decision = route("deep_planning")
        self.assertEqual(decision["selected_model"], "deepseek_v4_pro")

    def test_coding_routes_to_glm_5_1(self):
        decision = route("coding")
        self.assertEqual(decision["selected_model"], "glm_5_1")

    def test_review_routes_to_minimax_2_7(self):
        decision = route("review")
        self.assertEqual(decision["selected_model"], "minimax_2_7")

    def test_long_context_routes_to_kimi_2_6(self):
        decision = route("long_context")
        self.assertEqual(decision["selected_model"], "kimi_2_6")

    def test_unknown_task_uses_default(self):
        decision = route("nonexistent_task")
        self.assertIn(decision["task_type"], ("fast_intent", "nonexistent_task"))

    def test_local_only_privacy_returns_empty_model(self):
        decision = route("fast_intent", privacy_mode="local_only")
        self.assertEqual(decision["selected_model"], "")
        self.assertFalse(decision["allow_cloud"])

    def test_private_privacy_allows_cloud(self):
        decision = route("fast_intent", privacy_mode="private")
        self.assertEqual(decision["selected_model"], "qwen3")

    def test_decision_contains_no_api_keys(self):
        decision = route("coding")
        decision_str = str(decision)
        self.assertNotIn("api_key", decision_str)
        self.assertNotIn("GLM_API_KEY", decision_str)
        self.assertNotIn("DEEPSEEK_API_KEY", decision_str)
        self.assertNotIn("MINIMAX_API_KEY", decision_str)
        self.assertNotIn("QWEN_API_KEY", decision_str)
        self.assertNotIn("KIMI_API_KEY", decision_str)

    def test_decision_has_all_required_fields(self):
        decision = route("fast_intent")
        required = [
            "task_type", "preferred_model", "fallback_model",
            "selected_model", "reason", "timeout_seconds",
            "max_tokens", "privacy_mode", "allow_cloud", "fallback_used",
        ]
        for field in required:
            self.assertIn(field, decision, f"Missing field: {field}")

    def test_route_batch_returns_list(self):
        decisions = route_batch(["fast_intent", "coding", "review"])
        self.assertEqual(len(decisions), 3)
        self.assertEqual(decisions[0]["task_type"], "fast_intent")
        self.assertEqual(decisions[1]["task_type"], "coding")
        self.assertEqual(decisions[2]["task_type"], "review")

    def test_route_batch_handles_unknown_type(self):
        decisions = route_batch(["fast_intent", "unknown", "coding"])
        self.assertEqual(len(decisions), 3)

    def test_fallback_chain_exhausted(self):
        for model in ProviderRegistry.list_model_names():
            ProviderRegistry.disable(model)
        decision = route("fast_intent")
        self.assertEqual(decision["selected_model"], "")

    def test_experimental_model_mimo_disabled(self):
        decision = route("experimental")
        self.assertNotIn(decision["selected_model"], "mimo")

    def test_check_connectivity_for_unknown_model(self):
        result = check_connectivity("nonexistent")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "Unknown model")

    def test_check_connectivity_for_disabled_model(self):
        ProviderRegistry.disable("mimo")
        result = check_connectivity("mimo")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "Provider disabled")


class TestProviderRegistryValidation(unittest.TestCase):
    def setUp(self):
        ProviderRegistry.reset()
        ProviderRegistry.load_defaults()

    def test_privacy_modes_are_valid(self):
        self.assertIn("normal", PRIVACY_MODES)
        self.assertIn("private", PRIVACY_MODES)
        self.assertIn("local_only", PRIVACY_MODES)

    def test_default_providers_have_required_fields(self):
        for model_name, config in DEFAULT_PROVIDERS.items():
            self.assertIn("provider_name", config, f"{model_name} missing provider_name")
            self.assertIn("model_name", config, f"{model_name} missing model_name")
            self.assertIn("endpoint", config, f"{model_name} missing endpoint")
            self.assertIn("api_key_env", config, f"{model_name} missing api_key_env")
            self.assertIn("enabled", config, f"{model_name} missing enabled")

    def test_all_providers_have_different_model_names(self):
        names = [c["model_name"] for c in DEFAULT_PROVIDERS.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_every_model_in_policy_has_provider(self):
        for task_type, policy in ROUTING_POLICY.items():
            for role in ("preferred", "fallback"):
                model = policy[role]
                self.assertIn(model, DEFAULT_PROVIDERS,
                              f"Policy {task_type} references {model} but no provider config exists")


if __name__ == "__main__":
    unittest.main()
