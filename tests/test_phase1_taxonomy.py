from intent.taxonomy import ROUTES, NEXI_INTENTS, ALL_INTENTS, validate_route, validate_intent


def test_nexi_route_in_routes():
    assert "nexi" in ROUTES


def test_nexi_intents_count():
    assert len(NEXI_INTENTS) == 9


def test_validate_route_nexi():
    assert validate_route("nexi") == "nexi"


def test_validate_intent_nexi():
    assert validate_intent("run_agent") == "run_agent"
    assert validate_intent("invalid_nexi") == "unknown"


def test_nexi_intents_subset_of_all():
    for intent in NEXI_INTENTS:
        assert intent in ALL_INTENTS
