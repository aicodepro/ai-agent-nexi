from intent.feature_registry import discover_features, build_router_prompt, route_for


def test_route_for_derivation():
    assert route_for("open_app") == "local_action"
    assert route_for("agent_status") == "jarvis"
    assert route_for("general_qa") == "brain"


def test_discover_includes_core_features():
    feats = {f["intent"]: f for f in discover_features()}
    assert "open_app" in feats and feats["open_app"]["route"] == "local_action"
    assert "agent_status" in feats and feats["agent_status"]["route"] == "jarvis"
    assert "general_qa" in feats and feats["general_qa"]["route"] == "brain"


def test_every_feature_has_description():
    for f in discover_features():
        assert f["description"]
        assert f["route"] in {"local_action", "jarvis", "brain", "output"}


def test_prompt_lists_features_and_json_contract():
    prompt = build_router_prompt()
    assert "open_app" in prompt
    assert "general_qa" in prompt
    assert "STRICT JSON" in prompt
    assert "misheard" in prompt  # tolerates noisy ASR


def test_new_feature_auto_discovered():
    # Adding a skill must teach the router automatically — no prompt edits.
    from skills import dispatch
    dispatch.SKILL_MAP["teleport"] = lambda e: {"handled": True, "message": "zap"}
    try:
        intents = {f["intent"] for f in discover_features()}
        assert "teleport" in intents
        assert "teleport" in build_router_prompt()
    finally:
        dispatch.SKILL_MAP.pop("teleport", None)
