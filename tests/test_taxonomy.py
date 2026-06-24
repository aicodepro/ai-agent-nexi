from intent.taxonomy import (
    ROUTES, ALL_INTENTS, BRAIN_INTENTS, OUTPUT_INTENTS, LOCAL_INTENTS,
    empty_result, validate_route, validate_intent,
)


def test_all_intents_are_valid():
    for intent in ALL_INTENTS:
        assert validate_intent(intent) == intent


def test_brain_intents_subset():
    for intent in BRAIN_INTENTS:
        assert intent in ALL_INTENTS


def test_output_intents_subset():
    for intent in OUTPUT_INTENTS:
        assert intent in ALL_INTENTS


def test_local_intents_subset():
    for intent in LOCAL_INTENTS:
        assert intent in ALL_INTENTS


def test_all_routes_are_valid():
    for route in ROUTES:
        assert validate_route(route) == route


def test_brain_routes_valid():
    for route in ROUTES:
        validated = validate_route(route)
        assert validated in ROUTES


def test_empty_result():
    result = empty_result()
    assert result == {"route": "unknown", "intent": "unknown",
                       "confidence": 0.0, "entity": "", "reason": "no_match"}


def test_unknown_intent():
    assert validate_intent("totally_invalid_intent_xyz") == "unknown"


def test_unknown_route():
    assert validate_route("totally_invalid_route_xyz") == "unknown"


def test_known_intents_not_unknown():
    assert validate_intent("math") == "math"
    assert validate_intent("greeting") == "greeting"
    assert validate_intent("sleep") == "sleep"
    assert validate_intent("wake") == "wake"
    assert validate_intent("open_app") == "open_app"
    assert validate_intent("get_time") == "get_time"
    assert validate_intent("remember") == "remember"


def test_routes_contains_essential():
    essential = {"local_action", "brain", "system", "greeting", "identity",
                 "memory", "sleep", "unknown"}
    for r in essential:
        assert r in ROUTES, f"Missing essential route: {r}"
