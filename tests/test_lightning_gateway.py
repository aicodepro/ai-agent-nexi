import json
import os
import unittest
from unittest.mock import patch, MagicMock


class TestLightningConfig(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "LIGHTNING_API_BASE": "https://lightning.ai/v1",
            "LIGHTNING_AUTH_BASE64": "dGVzdDp0ZXN0",
            "LIGHTNING_AGENT_ID": "agent_123",
            "LIGHTNING_BILLING_PROJECT_ID": "proj_456",
            "LIGHTNING_STREAM": "true",
            "LIGHTNING_TIMEOUT_SECONDS": "90",
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()


class TestMissingConfig(TestLightningConfig):
    def test_missing_api_base_returns_safe_error(self):
        with patch.dict(os.environ, {"LIGHTNING_API_BASE": ""}, clear=False):
            from engine.lightning_gateway import ask_lightning
            result = ask_lightning("hello")
            self.assertEqual(result, "Brain connection is not configured.")

    def test_missing_auth_returns_safe_error(self):
        with patch.dict(os.environ, {"LIGHTNING_AUTH_BASE64": ""}, clear=False):
            from engine.lightning_gateway import ask_lightning
            result = ask_lightning("hello")
            self.assertEqual(result, "Brain connection is not configured.")

    def test_missing_agent_id_returns_safe_error(self):
        with patch.dict(os.environ, {"LIGHTNING_AGENT_ID": ""}, clear=False):
            from engine.lightning_gateway import ask_lightning
            result = ask_lightning("hello")
            self.assertEqual(result, "Brain connection is not configured.")

    def test_all_missing_returns_safe_error(self):
        with patch.dict(os.environ, {
            "LIGHTNING_API_BASE": "",
            "LIGHTNING_AUTH_BASE64": "",
            "LIGHTNING_AGENT_ID": "",
        }, clear=False):
            from engine.lightning_gateway import ask_lightning
            result = ask_lightning("hello")
            self.assertEqual(result, "Brain connection is not configured.")


class TestStreamParser(TestLightningConfig):
    def test_concatenates_delta_content(self):
        from engine.lightning_gateway import _parse_stream_chunks
        chunks = [
            {"result": {"choices": [{"delta": {"content": "Hello"}}]}},
            {"result": {"choices": [{"delta": {"content": " world"}}]}},
        ]
        raw = "\n".join(json.dumps(c) for c in chunks).encode("utf-8")
        result = _parse_stream_chunks(raw)
        self.assertEqual(result, "Hello world")

    def test_sse_data_lines_supported(self):
        from engine.lightning_gateway import _parse_stream_chunks
        chunk = {"result": {"choices": [{"delta": {"content": "Four"}}]}}
        raw = f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
        result = _parse_stream_chunks(raw)
        self.assertEqual(result, "Four")

    def test_ignores_malformed_chunks(self):
        from engine.lightning_gateway import _parse_stream_chunks
        raw = b"not json\ndata: {bad\n\n{\"result\":{\"choices\":[{\"delta\":{\"content\":\"OK\"}}]}}"
        result = _parse_stream_chunks(raw)
        self.assertEqual(result, "OK")

    def test_stops_on_finish_reason(self):
        from engine.lightning_gateway import _parse_stream_chunks
        chunks = [
            {"result": {"choices": [{"delta": {"content": "Part1"}}]}},
            {"result": {"choices": [{"delta": {"content": "Part2"}, "finish_reason": "stop"}]}},
            {"result": {"choices": [{"delta": {"content": "SHOULD_NOT_APPEAR"}}]}},
        ]
        raw = "\n".join(json.dumps(c) for c in chunks).encode("utf-8")
        result = _parse_stream_chunks(raw)
        self.assertEqual(result, "Part1Part2")
        self.assertNotIn("SHOULD_NOT_APPEAR", result)

    def test_empty_chunks_returns_empty(self):
        from engine.lightning_gateway import _parse_stream_chunks
        result = _parse_stream_chunks(b"")
        self.assertEqual(result, "")

    def test_skip_event_lines(self):
        from engine.lightning_gateway import _parse_stream_chunks
        lines = (
            b"event: ping\n"
            b"data: {\"result\":{\"choices\":[{\"delta\":{\"content\":\"Pong\"}}]}}\n"
        )
        result = _parse_stream_chunks(lines)
        self.assertEqual(result, "Pong")


class TestNonStreamParser(TestLightningConfig):
    def test_parses_choices_message_content(self):
        from engine.lightning_gateway import _parse_non_stream_body
        body = json.dumps({"choices": [{"message": {"content": "2+2=4"}}]}).encode("utf-8")
        result = _parse_non_stream_body(body)
        self.assertEqual(result, "2+2=4")

    def test_parses_result_field_fallback(self):
        from engine.lightning_gateway import _parse_non_stream_body
        body = json.dumps({"result": "fallback answer"}).encode("utf-8")
        result = _parse_non_stream_body(body)
        self.assertEqual(result, "fallback answer")

    def test_returns_empty_on_junk(self):
        from engine.lightning_gateway import _parse_non_stream_body
        result = _parse_non_stream_body(b"\xff\xfe")
        self.assertEqual(result, "")


class TestNoSecretLogged(TestLightningConfig):
    def test_no_secret_logged(self):
        from engine.lightning_gateway import _load_config
        api_base, auth_b64, project_id, agent_id, stream, timeout = _load_config()
        self.assertNotIn("Basic", auth_b64)
        self.assertEqual(auth_b64, "dGVzdDp0ZXN0")


class TestHTTPCall(TestLightningConfig):
    @patch("engine.lightning_gateway.urlopen")
    def test_successful_stream_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        chunks = [
            {"result": {"choices": [{"delta": {"content": "Four"}}]}},
            {"result": {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]}},
        ]
        raw = "\n".join(json.dumps(c) for c in chunks).encode("utf-8")
        mock_response.read.return_value = raw
        mock_urlopen.return_value = mock_response

        from engine.lightning_gateway import ask_lightning
        result = ask_lightning("what is 2+2")
        self.assertEqual(result, "Four")

    @patch("engine.lightning_gateway.urlopen")
    def test_http_error_returns_empty(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            url="", code=401, msg="Unauthorized", hdrs=None, fp=None
        )
        from engine.lightning_gateway import ask_lightning
        result = ask_lightning("hello")
        self.assertEqual(result, "")

    @patch("engine.lightning_gateway.urlopen")
    def test_connection_error_returns_empty(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("connection refused")
        from engine.lightning_gateway import ask_lightning
        result = ask_lightning("hello")
        self.assertEqual(result, "")


class TestResponseIsVoiceFriendly(TestLightningConfig):
    @patch("engine.lightning_gateway.urlopen")
    def test_response_is_voice_friendly_short(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        response_text = "Two plus two is four."
        chunk = {"result": {"choices": [{"delta": {"content": response_text}}]}}
        raw = json.dumps(chunk).encode("utf-8")
        mock_response.read.return_value = raw
        mock_urlopen.return_value = mock_response

        from engine.lightning_gateway import ask_lightning
        result = ask_lightning("what is 2+2")
        self.assertTrue(len(result.split()) <= 20,
                        f"Response too long: {len(result.split())} words")
        self.assertIn("four", result.lower())


if __name__ == "__main__":
    unittest.main()
