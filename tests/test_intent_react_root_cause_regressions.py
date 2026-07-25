from pathlib import Path


def test_react_schema_exposes_only_enabled_non_mutating_studio_tools():
    from engine.tool_registry import tools_openai_schema

    schemas = {item["function"]["name"]: item["function"] for item in tools_openai_schema()}
    assert "nexi_start_studio_build" not in schemas
    assert "nexi_cancel_studio_build" not in schemas
    assert "nexi_continue_studio_build" not in schemas
    assert "nexi_studio_status" in schemas
    assert "query" in schemas["recall_memory"]["parameters"]["properties"]
    assert "content" in schemas["create_file"]["parameters"]["properties"]


def test_create_file_writes_optional_content_and_preserves_empty_default(tmp_path, monkeypatch):
    from pathlib import Path

    from engine.tool_registry import execute_tool

    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")
    # create_file now confines writes to <home>/Desktop, so it takes a NAME, not a path.
    # Point home at tmp_path so the test exercises the real confinement without writing to
    # the developer's actual Desktop.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    assert execute_tool("create_file", {"file_name": "populated.txt", "content": "hello"})["success"] is True
    assert execute_tool("create_file", {"file_name": "empty.txt"})["success"] is True
    assert (desktop / "populated.txt").read_text(encoding="utf-8") == "hello"
    assert (desktop / "empty.txt").read_text(encoding="utf-8") == ""


def test_create_file_rejects_paths_outside_the_safe_root(tmp_path, monkeypatch):
    """file_name comes from ASR text, so it is untrusted: an absolute path or a traversal
    must not let a voice command write anywhere on disk."""
    from pathlib import Path

    from engine.tool_registry import execute_tool

    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Desktop").mkdir()

    for evil in (str(tmp_path / "escaped.txt"), "../escaped.txt", "..\\escaped.txt"):
        result = execute_tool("create_file", {"file_name": evil})
        assert result["success"] is False, f"{evil!r} was allowed to escape the safe root"
        assert result["error_code"] == "PATH_OUTSIDE_SAFE_ROOT"
    assert not (tmp_path / "escaped.txt").exists()


def test_intent_prompt_routes_compound_executable_requests_to_react():
    prompt = Path("prompts/nexi_groq_intent_system_prompt.txt").read_text(encoding="utf-8")
    assert "use route=react and intent=react_multi_step" in prompt


def test_runtime_status_registry_aliases_route_without_provider(monkeypatch):
    from engine.groq_intent_router_v2 import route_intent_v2

    monkeypatch.setenv("NEXI_ROUTER_HYBRID", "0")
    for phrase in ("agent runtime status", "show agent providers"):
        result = route_intent_v2(phrase, source="typed", context={"source": "typed"})
        assert result["route"] == "tool"
        assert result["intent"] == "nexi_agent_runtime_status"
