import os
import unittest
from unittest.mock import patch, MagicMock


def _reset_brain_fail_fast():
    try:
        from engine import features
        features._brain_fail_until = 0.0
    except Exception:
        pass


class TestBrainRouting(unittest.TestCase):
    """These tests target the Lightning-side of the chain. They explicitly
    force Lightning as primary via the new env vars so the mocked Lightning
    response is exercised. The default chain (hugchat first) is covered in
    tests/test_brain_provider_priority.py."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS": "true",
            "NEXI_BRAIN_PRIMARY": "lightning",
            "NEXI_BRAIN_FALLBACK": "hugchat",
            "NEXI_BRAIN_PROVIDER": "",
            "LIGHTNING_API_BASE": "https://lightning.ai/v1",
            "LIGHTNING_AUTH_BASE64": "dGVzdDp0ZXN0",
            "LIGHTNING_AGENT_ID": "agent_123",
        })
        self.env_patcher.start()
        _reset_brain_fail_fast()

    def tearDown(self):
        _reset_brain_fail_fast()
        self.env_patcher.stop()


class TestQARoutesToLightning(TestBrainRouting):
    @patch("engine.lightning_gateway.urlopen")
    def test_qa_routes_to_lightning(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        chunk = {"result": {"choices": [{"delta": {"content": "Hello! How can I help you?"}}]}}
        mock_response.read.return_value = json.dumps(chunk).encode("utf-8")
        mock_urlopen.return_value = mock_response

        from engine.features import chatBot
        with patch("engine.features.speak") as mock_speak:
            result = chatBot("hello")
            self.assertIn("Hello", result)
            mock_speak.assert_called_once_with(result)

    @patch("engine.lightning_gateway.urlopen")
    def test_what_is_2_plus_2_routes_to_lightning(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        chunk = {"result": {"choices": [{"delta": {"content": "Two plus two is four."}}]}}
        mock_response.read.return_value = json.dumps(chunk).encode("utf-8")
        mock_urlopen.return_value = mock_response

        from engine.features import chatBot
        with patch("engine.features.speak") as mock_speak:
            result = chatBot("what is 2+2")
            self.assertIn("four", result.lower())
            mock_speak.assert_called_once_with(result)


class TestOpenChromeDoesNotRouteToLightning(TestBrainRouting):
    @patch("engine.features.openCommand")
    def test_open_chrome_does_not_route_to_lightning(self, mock_open):
        from engine.command import dispatch_intent
        handled = dispatch_intent("open chrome")
        self.assertTrue(handled)

    @patch("engine.file_operations.create_folder_and_files")
    def test_create_folder_does_not_route_to_lightning(self, mock_cff):
        from engine.command import dispatch_intent
        handled = dispatch_intent("create folder")
        self.assertTrue(handled)

    @patch("engine.features.openCommand")
    def test_open_notepad_does_not_route_to_lightning(self, mock_open):
        from engine.command import dispatch_intent
        handled = dispatch_intent("open notepad")
        self.assertTrue(handled)

    @patch("engine.command.speak")
    def test_joke_stays_local(self, mock_speak):
        from engine.command import dispatch_intent
        handled = dispatch_intent("tell me a joke")
        self.assertTrue(handled)

    @patch("engine.command.speak")
    def test_time_stays_local(self, mock_speak):
        from engine.command import dispatch_intent
        handled = dispatch_intent("what is the time")
        self.assertTrue(handled)

    @patch("engine.command.speak")
    def test_weather_stays_local(self, mock_speak):
        from engine.command import dispatch_intent
        handled = dispatch_intent("what is the weather")
        self.assertTrue(handled)

    @patch("engine.command.speak")
    def test_close_app_stays_local(self, mock_speak):
        from engine.command import dispatch_intent
        handled = dispatch_intent("close chrome")
        self.assertTrue(handled)


class TestFallbackWhenLightningMissing(unittest.TestCase):
    # Legacy opt-in chain: HugChat primary -> Lightning fallback -> safe error.
    @patch.dict(os.environ, {
        "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS": "true",
        "NEXI_BRAIN_PRIMARY": "hugchat",
        "NEXI_BRAIN_FALLBACK": "lightning",
        "NEXI_BRAIN_PROVIDER": "",
        "LIGHTNING_API_BASE": "",
    }, clear=False)
    def test_all_providers_unavailable_returns_safe_message(self):
        _reset_brain_fail_fast()
        from engine.features import chatBot
        # HugChat cookies missing AND Lightning unconfigured -> safe error.
        with patch("engine.features.os.path.exists", return_value=False), \
             patch("engine.features.speak") as mock_speak:
            result = chatBot("hello")
            self.assertIn("local actions are working", result.lower())
            mock_speak.assert_called_once_with(result)

    @patch.dict(os.environ, {
        "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS": "true",
        "NEXI_BRAIN_PRIMARY": "hugchat",
        "NEXI_BRAIN_FALLBACK": "lightning",
        "NEXI_BRAIN_PROVIDER": "",
        "LIGHTNING_API_BASE": "",
    }, clear=False)
    def test_lightning_unconfigured_after_hugchat_fail_returns_safe(self):
        _reset_brain_fail_fast()
        from engine.features import chatBot
        with patch("engine.features.os.path.exists", return_value=False), \
             patch("engine.features.speak") as mock_speak:
            result = chatBot("hello")
            self.assertIn("local actions are working", result.lower())
            mock_speak.assert_called_once_with(result)


class TestNoSecretsInRouting(unittest.TestCase):
    @patch.dict(os.environ, {
        "NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS": "true",
        "NEXI_BRAIN_PROVIDER": "lightning",
        "LIGHTNING_API_BASE": "https://lightning.ai/v1",
        "LIGHTNING_AUTH_BASE64": "dGVzdDp0ZXN0",
        "LIGHTNING_AGENT_ID": "agent_123",
    }, clear=False)
    @patch("engine.lightning_gateway.urlopen")
    def test_no_secret_logged_in_routing(self, mock_urlopen):
        import io
        captured = io.StringIO()
        import sys
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            mock_response = MagicMock()
            mock_response.status = 200
            chunk = {"result": {"choices": [{"delta": {"content": "Hello"}}]}}
            mock_response.read.return_value = json.dumps(chunk).encode("utf-8")
            mock_urlopen.return_value = mock_response

            _reset_brain_fail_fast()
            from engine.features import chatBot
            with patch("engine.features.speak"):
                chatBot("hello")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        self.assertNotIn("dGVzdDp0ZXN0", output)
        self.assertNotIn("Authorization", output)
        self.assertNotIn("Basic ", output)


import json


if __name__ == "__main__":
    unittest.main()
