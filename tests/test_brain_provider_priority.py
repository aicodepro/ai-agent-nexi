import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Force a clean known env for every test."""
    monkeypatch.setenv("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS", "true")
    monkeypatch.setenv("NEXI_BRAIN_PRIMARY", "hugchat")
    monkeypatch.setenv("NEXI_BRAIN_FALLBACK", "lightning")
    monkeypatch.delenv("NEXI_BRAIN_PROVIDER", raising=False)
    from engine import features
    features._brain_fail_until = 0.0
    yield
    features._brain_fail_until = 0.0


# ---------------------------------------------------------------------------
# Provider precedence (regression for the double-audit bug)
# ---------------------------------------------------------------------------

def test_default_chain_is_gemini_only(monkeypatch):
    """No env vars set -> Gemini Flash is the only provider chain entry."""
    from engine import features
    monkeypatch.delenv("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_PRIMARY", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_FALLBACK", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_PROVIDER", raising=False)
    assert features._resolve_provider_chain() == ["gemini"]


def test_legacy_brain_provider_ignored_without_legacy_enable(monkeypatch):
    """Stale legacy env must not override Gemini unless legacy is enabled."""
    from engine import features
    monkeypatch.setenv("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS", "false")
    monkeypatch.delenv("NEXI_BRAIN_PRIMARY", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_FALLBACK", raising=False)
    monkeypatch.setenv("NEXI_BRAIN_PROVIDER", "lightning")
    chain = features._resolve_provider_chain()
    assert chain == ["gemini"]


def test_explicit_primary_lightning_is_honored(monkeypatch):
    """If a user explicitly sets NEXI_BRAIN_PRIMARY=lightning, honour it."""
    from engine import features
    monkeypatch.setenv("NEXI_BRAIN_PRIMARY", "lightning")
    monkeypatch.delenv("NEXI_BRAIN_FALLBACK", raising=False)
    chain = features._resolve_provider_chain()
    assert chain[0] == "lightning"
    assert chain == ["lightning"]


# ---------------------------------------------------------------------------
# Provider chain
# ---------------------------------------------------------------------------

def test_general_question_tries_hugchat_first():
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="Two plus two is four.") as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning") as mock_light:
        result = features.ask_brain("what is 2+2")
        mock_hug.assert_called_once_with("what is 2+2")
        mock_light.assert_not_called()
        assert "four" in result.lower()


def test_hugchat_success_does_not_call_lightning():
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="Paris is the capital of France.") as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning") as mock_light:
        result = features.ask_brain("what is the capital of france")
        mock_hug.assert_called_once()
        mock_light.assert_not_called()
        assert "Paris" in result


def test_hugchat_exception_falls_back_to_lightning():
    from engine import features
    with patch.object(features, "ask_hugchat", side_effect=RuntimeError("hugchat down")) as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", return_value="Fallback answer.") as mock_light:
        result = features.ask_brain("explain solar system")
        mock_hug.assert_called_once()
        mock_light.assert_called_once_with("explain solar system")
        assert result == "Fallback answer."


def test_hugchat_missing_cookies_falls_back_to_lightning():
    from engine import features
    with patch.object(features, "ask_hugchat", side_effect=FileNotFoundError("cookies missing")) as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", return_value="Lightning got it.") as mock_light:
        result = features.ask_brain("why is the sky blue")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert result == "Lightning got it."


def test_hugchat_empty_response_falls_back_to_lightning():
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="") as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", return_value="Lightning answers.") as mock_light:
        result = features.ask_brain("what is 2+2")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert result == "Lightning answers."


def test_hugchat_none_response_falls_back_to_lightning():
    from engine import features
    with patch.object(features, "ask_hugchat", return_value=None) as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", return_value="OK.") as mock_light:
        result = features.ask_brain("any question")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert result == "OK."


def test_hugchat_failure_text_falls_back_to_lightning():
    """If HugChat returns a known failure marker text, treat it as failed."""
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="Sorry, not ready.") as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", return_value="Real answer.") as mock_light:
        result = features.ask_brain("what is python")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert result == "Real answer."


def test_lightning_failure_returns_safe_error():
    from engine import features
    with patch.object(features, "ask_hugchat", side_effect=RuntimeError("hugchat down")) as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", side_effect=RuntimeError("lightning down")) as mock_light:
        result = features.ask_brain("explain anything")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert "local actions are working" in result.lower()


def test_both_providers_empty_returns_safe_error():
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="") as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning", return_value="") as mock_light:
        result = features.ask_brain("any question")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert "local actions are working" in result.lower()


def test_lightning_not_configured_falls_through_to_safe_error():
    """Lightning returning 'Brain connection is not configured.' must be
    treated as a failure, not a real answer."""
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="") as mock_hug, \
         patch("engine.lightning_gateway.ask_lightning",
               return_value="Brain connection is not configured.") as mock_light:
        result = features.ask_brain("what is 2+2")
        mock_hug.assert_called_once()
        mock_light.assert_called_once()
        assert "local actions are working" in result.lower()


# ---------------------------------------------------------------------------
# chatBot speaks exactly once
# ---------------------------------------------------------------------------

def test_chatbot_speaks_once_on_success():
    from engine import features
    with patch.object(features, "ask_hugchat", return_value="Hello back."), \
         patch.object(features, "speak") as mock_speak:
        result = features.chatBot("hello")
        mock_speak.assert_called_once_with("Hello back.")
        assert result == "Hello back."


def test_chatbot_speaks_once_on_full_failure():
    from engine import features
    with patch.object(features, "ask_hugchat", side_effect=RuntimeError("down")), \
         patch("engine.lightning_gateway.ask_lightning", side_effect=RuntimeError("down")), \
         patch.object(features, "speak") as mock_speak:
        result = features.chatBot("any")
        mock_speak.assert_called_once()
        assert "local actions are working" in result.lower()


# ---------------------------------------------------------------------------
# Local commands bypass the brain provider entirely
# ---------------------------------------------------------------------------

def test_open_chrome_does_not_call_brain_provider():
    """When the router classifies as local_action, chatBot/ask_brain
    must not be called by allCommands."""
    from engine.intent_router import route_intent
    r = route_intent("open chrome")
    assert r.route == "local_action"

    # Confirm allCommands does not invoke chatBot for local actions.
    # With v2 LLM-first routing, the intent is handled as tool/open_app
    # and dispatch_intent is bypassed entirely.
    import engine.command as command
    from engine.local_skills import SkillResult
    with patch("engine.features.chatBot") as mock_chat, \
         patch("engine.command.dispatch_intent", return_value=True) as mock_disp, \
         patch("engine.command.eel"), \
         patch("engine.command.speak"), \
         patch("engine.local_skills.handle_local_skill",
               return_value=SkillResult(False)):
        command.allCommands("open chrome")
        mock_chat.assert_not_called()
        mock_disp.assert_not_called()


def test_create_folder_does_not_call_brain_provider():
    from engine.intent_router import route_intent
    r = route_intent("create folder")
    assert r.route == "local_action"

    import engine.command as command
    from engine import workflow_state
    workflow_state.clear_workflow()
    with patch("engine.features.chatBot") as mock_chat, \
         patch("engine.command.dispatch_intent", return_value=True) as mock_disp, \
         patch("engine.command.eel"), \
         patch("engine.command.speak"):
        command.allCommands("create folder")
        mock_chat.assert_not_called()
        mock_disp.assert_not_called()
    # Clean up any followup/workflow state this test leaves behind
    from engine.followup_manager import clear_followup
    clear_followup("test_cleanup")


def test_cancel_does_not_call_brain_provider():
    """Bare 'cancel' / 'stop' without active workflow must stay local."""
    from engine.intent_router import route_intent
    for q in ("cancel", "stop"):
        r = route_intent(q, workflow_active=False)
        assert r.route != "brain", f"{q!r} routed to brain, must stay local"


# ---------------------------------------------------------------------------
# Routing decisions (compatibility with intent_router rename)
# ---------------------------------------------------------------------------

def test_what_is_2_plus_2_does_not_route_to_greeting():
    from engine.intent_router import route_intent
    r = route_intent("what is 2+2")
    assert r.route != "greeting"
    assert r.route != "identity"
    assert r.route == "brain"


def test_hello_routes_to_greeting_not_brain():
    from engine.intent_router import route_intent
    r = route_intent("hello")
    assert r.route == "greeting"
    assert r.route != "brain"


def test_who_are_you_routes_to_identity_not_brain():
    from engine.intent_router import route_intent
    r = route_intent("who are you")
    assert r.route == "identity"
    assert r.route != "brain"


# ---------------------------------------------------------------------------
# Secret-leak guard
# ---------------------------------------------------------------------------

def test_no_secret_logged_in_provider_chain(capsys, monkeypatch):
    """Provider chain logs must not contain auth, cookies, or env values."""
    monkeypatch.setenv("LIGHTNING_AUTH_BASE64", "SECRET_TOKEN_dGVzdDp0ZXN0")
    from engine import features
    with patch.object(features, "ask_hugchat", side_effect=RuntimeError("conn err")), \
         patch("engine.lightning_gateway.ask_lightning", return_value="ok"):
        features.ask_brain("hello")
    out = capsys.readouterr().out
    assert "SECRET_TOKEN_dGVzdDp0ZXN0" not in out
    assert "Authorization" not in out
    assert "Basic " not in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
