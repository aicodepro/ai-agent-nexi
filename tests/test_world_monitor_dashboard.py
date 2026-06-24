import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_world_monitor_dashboard_returns_json_safe_state():
    from engine.world_monitor_dashboard import WorldMonitorDashboard
    state = WorldMonitorDashboard().get_dashboard_state()
    json.dumps(state)
    ids = {panel["id"] for panel in state["panels"]}
    assert {"system", "memory", "active", "tools", "commands", "routes", "brain", "wake"}.issubset(ids)
    assert state["panel_count"] == len(state["panels"])


def test_world_monitor_dashboard_get_panel():
    from engine.world_monitor_dashboard import WorldMonitorDashboard
    panel = WorldMonitorDashboard().get_panel("tools")
    assert panel is not None
    assert panel.id == "tools"
    assert "total" in panel.data


def test_command_exposes_dashboard_state():
    import engine.command as command
    payload = json.loads(command.getDashboardState())
    assert "panels" in payload
    assert payload["version"] == 1
