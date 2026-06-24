from skills.dispatch import SKILL_MAP, handle_skill
from intent.taxonomy import NEXI_INTENTS


def test_nexi_skill_map_has_all_intents():
    for intent in NEXI_INTENTS:
        assert intent in SKILL_MAP, f"Missing SKILL_MAP entry for {intent}"


def test_handle_nexi_skill():
    result = handle_skill("agent_status", "")
    assert isinstance(result, dict)
    assert result.get("handled")
    assert isinstance(result.get("message"), str)
    assert "Nexi route" in result.get("message", "")
