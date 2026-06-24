from intent.router import route_intent


def test_jarvis_run_agent():
    result = route_intent("run agent deploy my app")
    assert result["route"] == "jarvis"
    assert result["intent"] == "run_agent"


def test_jarvis_add_rule():
    result = route_intent("add rule when i say open chrome do edge")
    assert result["route"] == "jarvis"
    assert result["intent"] == "add_rule"


def test_jarvis_agent_status():
    result = route_intent("agent status")
    assert result["route"] == "jarvis"
    assert result["intent"] == "agent_status"


def test_jarvis_cancel_agent():
    result = route_intent("stop agent")
    assert result["route"] == "jarvis"
    assert result["intent"] == "cancel_agent"


def test_jarvis_train_on_correction():
    result = route_intent("train on that")
    assert result["route"] == "jarvis"
    assert result["intent"] == "train_on_correction"


def test_jarvis_execute_tool():
    result = route_intent("execute tool chrome")
    assert result["route"] == "jarvis"
    assert result["intent"] == "execute_tool"


def test_jarvis_reflect():
    result = route_intent("reflect on that")
    assert result["route"] == "jarvis"
    assert result["intent"] == "reflect"


def test_existing_list_tools_still_works():
    result = route_intent("list tools")
    assert result["route"] == "tool"
    assert result["intent"] == "list_tools"


def test_existing_show_rules_still_works():
    result = route_intent("show rules")
    assert result["route"] == "training"
    assert result["intent"] == "show_rules"


def test_existing_when_i_say_still_works():
    result = route_intent("when i say hello do greet")
    assert result["route"] == "training"
    assert result["intent"] == "train_rule"


def test_existing_plan_still_works():
    result = route_intent("plan my day")
    assert result["route"] == "workflow"
    assert result["intent"] == "run_plan"
