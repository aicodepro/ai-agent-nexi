from intent.taxonomy import ROUTES, JARVIS_INTENTS, ALL_INTENTS, validate_route, validate_intent


def test_jarvis_route_in_routes():
    assert "jarvis" in ROUTES


def test_jarvis_intents_count():
    assert len(JARVIS_INTENTS) == 9


def test_validate_route_jarvis():
    assert validate_route("jarvis") == "jarvis"


def test_validate_intent_jarvis():
    assert validate_intent("run_agent") == "run_agent"
    assert validate_intent("invalid_jarvis") == "unknown"


def test_jarvis_intents_subset_of_all():
    for intent in JARVIS_INTENTS:
        assert intent in ALL_INTENTS
