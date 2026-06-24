from skills.jarvis import agent_status, cancel_agent, run_agent, add_rule


def test_agent_status_returns_string():
    result = agent_status()
    assert isinstance(result, str)
    assert "Jarvis route" in result


def test_cancel_agent_returns_string():
    result = cancel_agent()
    assert isinstance(result, str)


def test_run_agent_returns_string():
    result = run_agent("deploy my app")
    assert isinstance(result, str)


def test_add_rule_returns_string():
    result = add_rule("when i say X do Y")
    assert isinstance(result, str)
