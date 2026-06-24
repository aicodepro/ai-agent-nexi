import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _manifest_entry(name, required_slots=None, risk_level="none", confirmation_required=False):
    return {
        "name": name,
        "description": f"{name} test entry",
        "required_slots": required_slots or [],
        "optional_slots": [],
        "risk_level": risk_level,
        "confirmation_required": confirmation_required,
        "aliases": [],
        "handler": name,
    }


def test_manifest_cannot_invent_executable_tools(tmp_path):
    from engine.tool_manifest_loader import load_tool_manifest, validate_manifest_entry

    valid_open_app = _manifest_entry("open_app", ["app_name"])
    invented = _manifest_entry("invented_shell_tool")
    path = tmp_path / "tool_manifest.json"
    path.write_text(json.dumps({"schema_version": "1.0", "tools": [valid_open_app, invented]}), encoding="utf-8")

    loaded = load_tool_manifest(path)
    names = [entry["name"] for entry in loaded["tools"]]

    assert "open_app" in names
    assert "invented_shell_tool" not in names
    assert validate_manifest_entry(invented) == (False, "tool_not_registered")


def test_router_tool_names_include_only_valid_manifest_entries(monkeypatch, tmp_path):
    import engine.tool_manifest_loader as loader

    path = tmp_path / "tool_manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tools": [
                    _manifest_entry("open_website", ["url"]),
                    _manifest_entry("invented_browser_launcher"),
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "MANIFEST_PATH", path)

    names = loader.tool_names_for_router()
    assert names == ["open_website"]
    assert "invented_browser_launcher" not in names
