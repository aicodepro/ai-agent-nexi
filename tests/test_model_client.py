import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from engine.brain.model_client import (
    ModelClient, MockModelClient, BlockedModelClient,
    make_request, make_success_response, make_error_response,
    validate_request,
)
from engine.brain.provider_factory import (
    create_client, create_client_for_decision, execute_via_router,
    execute_with_client,
)
from engine.brain.provider_registry import ProviderRegistry


class TestModelRequestResponseContracts(unittest.TestCase):
    def test_make_request_has_required_fields(self):
        req = make_request(model_name="test", task_type="coding")
        self.assertIn("model_name", req)
        self.assertIn("task_type", req)
        self.assertIn("messages", req)
        self.assertIn("prompt", req)
        self.assertIn("max_tokens", req)
        self.assertIn("timeout_seconds", req)
        self.assertIn("privacy_mode", req)
        self.assertIn("allow_cloud", req)
        self.assertIn("metadata", req)

    def test_make_request_defaults(self):
        req = make_request()
        self.assertEqual(req["model_name"], "")
        self.assertEqual(req["task_type"], "")
        self.assertEqual(req["messages"], [])
        self.assertEqual(req["prompt"], "")
        self.assertEqual(req["privacy_mode"], "normal")
        self.assertTrue(req["allow_cloud"])
        self.assertEqual(req["metadata"], {})

    def test_make_request_with_custom_values(self):
        req = make_request(
            model_name="glm_5_1", task_type="coding",
            prompt="Hello", messages=[{"role": "user", "content": "Hello"}],
            max_tokens=4096, timeout_seconds=60,
            privacy_mode="private", allow_cloud=False,
            metadata={"key": "value"},
        )
        self.assertEqual(req["model_name"], "glm_5_1")
        self.assertEqual(req["task_type"], "coding")
        self.assertEqual(req["prompt"], "Hello")
        self.assertEqual(len(req["messages"]), 1)
        self.assertEqual(req["max_tokens"], 4096)
        self.assertEqual(req["privacy_mode"], "private")
        self.assertFalse(req["allow_cloud"])
        self.assertEqual(req["metadata"]["key"], "value")

    def test_make_success_response_has_required_fields(self):
        resp = make_success_response(content="ok")
        self.assertTrue(resp["ok"])
        self.assertIn("model_name", resp)
        self.assertIn("provider_name", resp)
        self.assertIn("content", resp)
        self.assertIn("usage", resp)
        self.assertIn("input_tokens", resp["usage"])
        self.assertIn("output_tokens", resp["usage"])
        self.assertIn("latency_ms", resp)
        self.assertIsNone(resp["error"])

    def test_make_error_response_has_required_fields(self):
        resp = make_error_response(error_code="FAIL", error_message="Something broke")
        self.assertFalse(resp["ok"])
        self.assertIsNotNone(resp["error"])
        self.assertEqual(resp["error"]["code"], "FAIL")
        self.assertEqual(resp["error"]["message"], "Something broke")
        self.assertEqual(resp["content"], "")

    def test_no_secrets_in_error_response(self):
        resp = make_error_response(error_code="FAIL", error_message="error")
        resp_str = str(resp)
        self.assertNotIn("api_key", resp_str)
        self.assertNotIn("password", resp_str)
        self.assertNotIn("DEEPSEEK_API_KEY", resp_str)
        self.assertNotIn("GLM_API_KEY", resp_str)
        self.assertNotIn("MINIMAX_API_KEY", resp_str)

    def test_validate_request_valid(self):
        req = make_request(model_name="a", task_type="b", allow_cloud=True)
        valid, msg = validate_request(req)
        self.assertTrue(valid)
        self.assertEqual(msg, "")

    def test_validate_request_missing_field(self):
        valid, msg = validate_request({})
        self.assertFalse(valid)

    def test_validate_request_invalid_messages(self):
        req = make_request(model_name="a", task_type="b", allow_cloud=True)
        req["messages"] = "not a list"
        valid, msg = validate_request(req)
        self.assertFalse(valid)

    def test_validate_request_invalid_allow_cloud(self):
        req = make_request(model_name="a", task_type="b", allow_cloud=True)
        req["allow_cloud"] = "yes"
        valid, msg = validate_request(req)
        self.assertFalse(valid)


class TestMockModelClient(unittest.TestCase):
    def test_generate_returns_deterministic_success(self):
        client = MockModelClient(model_name="test_model", provider_name="test_provider")
        request = make_request(model_name="test_model", task_type="coding",
                               prompt="Write a test", allow_cloud=True)
        response = client.generate(request)
        self.assertTrue(response["ok"])
        self.assertEqual(response["model_name"], "test_model")
        self.assertEqual(response["provider_name"], "test_provider")
        self.assertIn("[Mock]", response["content"])

    def test_generate_simulates_failure(self):
        client = MockModelClient(model_name="test_model", provider_name="test_provider",
                                 simulate_failure=True)
        request = make_request(model_name="test_model", task_type="coding",
                               prompt="fail", allow_cloud=True)
        response = client.generate(request)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "INTERNAL_ERROR")
        self.assertEqual(response["error"]["message"], "Mock simulated failure")

    def test_generate_simulates_timeout(self):
        client = MockModelClient(model_name="test_model", provider_name="test_provider",
                                 simulate_timeout=True)
        request = make_request(model_name="test_model", task_type="coding",
                               prompt="timeout", allow_cloud=True)
        response = client.generate(request)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "TIMEOUT")

    def test_health_check_returns_ok(self):
        client = MockModelClient()
        result = client.health_check()
        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "mock_model")

    def test_health_check_returns_failure_when_simulated(self):
        client = MockModelClient(simulate_failure=True)
        result = client.health_check()
        self.assertFalse(result["ok"])

    def test_capabilities(self):
        client = MockModelClient()
        caps = client.get_capabilities()
        self.assertTrue(caps["vision"])
        self.assertTrue(caps["streaming"])
        self.assertTrue(caps["tools"])
        self.assertTrue(caps["long_context"])

    def test_call_count_increments(self):
        client = MockModelClient()
        req = make_request(model_name="m", task_type="t", prompt="test", allow_cloud=True)
        self.assertEqual(client.call_count(), 0)
        client.generate(req)
        self.assertEqual(client.call_count(), 1)
        client.generate(req)
        client.generate(req)
        self.assertEqual(client.call_count(), 3)

    def test_generate_rejects_invalid_request(self):
        client = MockModelClient()
        response = client.generate({"not": "valid"})
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "INVALID_REQUEST")

    def test_no_api_keys_in_mock_output(self):
        client = MockModelClient()
        req = make_request(model_name="m", task_type="t", prompt="test", allow_cloud=True)
        response = client.generate(req)
        response_str = str(response)
        self.assertNotIn("DEEPSEEK_API_KEY", response_str)
        self.assertNotIn("GLM_API_KEY", response_str)
        self.assertNotIn("MINIMAX_API_KEY", response_str)
        self.assertNotIn("QWEN_API_KEY", response_str)
        self.assertNotIn("KIMI_API_KEY", response_str)


class TestBlockedModelClient(unittest.TestCase):
    def test_blocked_returns_error(self):
        client = BlockedModelClient(model_name="unknown", reason="Test block")
        request = make_request(model_name="unknown", task_type="coding", allow_cloud=True)
        response = client.generate(request)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "BLOCKED")
        self.assertEqual(response["error"]["message"], "Test block")

    def test_blocked_health_check(self):
        client = BlockedModelClient(model_name="x", reason="blocked")
        result = client.health_check()
        self.assertFalse(result["ok"])

    def test_blocked_capabilities_all_false(self):
        client = BlockedModelClient()
        caps = client.get_capabilities()
        self.assertFalse(caps["vision"])
        self.assertFalse(caps["streaming"])
        self.assertFalse(caps["tools"])
        self.assertFalse(caps["long_context"])


class TestModelClientBase(unittest.TestCase):
    def test_base_generate_raises(self):
        client = ModelClient()
        with self.assertRaises(NotImplementedError):
            client.generate({})

    def test_base_health_check_raises(self):
        client = ModelClient()
        with self.assertRaises(NotImplementedError):
            client.health_check()

    def test_base_capabilities_default_false(self):
        client = ModelClient()
        caps = client.get_capabilities()
        self.assertFalse(caps["vision"])
        self.assertFalse(caps["streaming"])
        self.assertFalse(caps["tools"])
        self.assertFalse(caps["long_context"])

    def test_base_validate_request_works(self):
        client = ModelClient()
        valid, msg = client.validate_request(
            make_request(model_name="a", task_type="b", allow_cloud=True)
        )
        self.assertTrue(valid)


class TestProviderFactory(unittest.TestCase):
    def setUp(self):
        ProviderRegistry.reset()
        ProviderRegistry.load_defaults()

    def test_create_client_for_known_model(self):
        client = create_client("glm_5_1")
        self.assertIsInstance(client, MockModelClient)

    def test_create_client_for_unknown_model_returns_blocked(self):
        client = create_client("nonexistent_model")
        self.assertIsInstance(client, BlockedModelClient)

    def test_create_client_for_disabled_model_returns_blocked(self):
        ProviderRegistry.disable("minimax_2_7")
        client = create_client("minimax_2_7")
        self.assertIsInstance(client, BlockedModelClient)

    def test_local_only_blocks_cloud_model(self):
        client = create_client("deepseek_v4_pro", privacy_mode="local_only")
        self.assertIsInstance(client, BlockedModelClient)
        response = client.generate(make_request(allow_cloud=False))
        self.assertFalse(response["ok"])
        self.assertIn("blocked", response["error"]["message"].lower())

    def test_normal_privacy_allows_cloud(self):
        client = create_client("deepseek_v4_pro", privacy_mode="normal")
        self.assertIsInstance(client, MockModelClient)

    def test_private_privacy_allows_cloud(self):
        client = create_client("deepseek_v4_pro", privacy_mode="private")
        self.assertIsInstance(client, MockModelClient)

    def test_create_client_for_decision_returns_client(self):
        decision = {
            "selected_model": "glm_5_1",
            "privacy_mode": "normal",
            "task_type": "coding",
        }
        client = create_client_for_decision(decision)
        self.assertIsInstance(client, MockModelClient)

    def test_create_client_for_empty_decision_returns_blocked(self):
        client = create_client_for_decision({})
        self.assertIsInstance(client, BlockedModelClient)

    def test_create_client_for_none_decision_returns_blocked(self):
        client = create_client_for_decision(None)
        self.assertIsInstance(client, BlockedModelClient)

    def test_create_client_for_decision_no_selected_model(self):
        client = create_client_for_decision({"privacy_mode": "normal"})
        self.assertIsInstance(client, BlockedModelClient)

    def test_mock_client_works_with_request(self):
        client = create_client("qwen3", use_mock=True)
        request = make_request(model_name="qwen3", task_type="fast_intent",
                               prompt="hello", allow_cloud=True)
        response = client.generate(request)
        self.assertTrue(response["ok"])
        self.assertIn("[Mock]", response["content"])

    def test_factory_does_not_expose_api_keys(self):
        client = create_client("deepseek_v4_pro", use_mock=True)
        client_str = str(client.__dict__)
        self.assertNotIn("DEEPSEEK_API_KEY", client_str)
        self.assertNotIn("api_key", client_str.lower())


class TestExecuteViaRouter(unittest.TestCase):
    def setUp(self):
        ProviderRegistry.reset()
        ProviderRegistry.load_defaults()

    def test_execute_via_router_returns_mock_response(self):
        response = execute_via_router(
            task_type="coding", prompt="Write a test",
            use_mock=True,
        )
        self.assertTrue(response["ok"])
        self.assertIn("[Mock]", response["content"])

    def test_execute_via_router_local_only_returns_blocked(self):
        response = execute_via_router(
            task_type="coding", prompt="test",
            privacy_mode="local_only", use_mock=True,
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "NO_MODEL_AVAILABLE")

    def test_execute_with_client_returns_mock_response(self):
        client = MockModelClient(model_name="test", provider_name="test")
        response = execute_with_client(
            client, task_type="coding", prompt="hello",
        )
        self.assertTrue(response["ok"])
        self.assertIn("[Mock]", response["content"])

    def test_execute_with_blocked_client_returns_error(self):
        client = BlockedModelClient(model_name="x", reason="blocked")
        response = execute_with_client(
            client, task_type="coding", prompt="hello",
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
