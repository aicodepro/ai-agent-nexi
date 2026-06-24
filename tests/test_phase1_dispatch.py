from skills.dispatch import SKILL_MAP, handle_skill
from intent.taxonomy import JARVIS_INTENTS


def test_jarvis_skill_map_has_all_intents():
    for intent in JARVIS_INTENTS:
        assert intent in SKILL_MAP, f"Missing SKILL_MAP entry for {intent}"


def test_handle_jarvis_skill():
    result = handle_skill("agent_status", "")
    assert isinstance(result, dict)
    assert result.get("handled")
    assert isinstance(result.get("message"), str)
    assert "Jarvis route" in result.get("message", "")
