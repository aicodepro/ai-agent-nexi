"""MCP preflight — every server must connect (and expose tools) before any task runs.

Darsh's daily failure: "only 1-2 MCPs start, the rest fail; manual reconnect works."
Reproduced against his real .mcp.json: 1 of 5 up. Root cause is NOT flaky servers —
`npx -y <pkg>` downloads on a cold cache while the host's connect timeout is ~10s, so
the first start loses a race. Manual reconnect "works" because npx cached the package.

The two properties that make this useful (and that these tests pin):
  * a server that connects but exposes ZERO tools counts as DOWN — telling an agent a
    server is available when it has no tools is how phantom-tool hallucination starts;
  * failures are classified into a CAUSE + FIX, because "handshake_timeout" is a
    symptom nobody can act on, and retrying never fixes a missing binary or missing key.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.agent_runtime import mcp_preflight as mp


# ---- config loading ------------------------------------------------------------

def test_loads_servers_from_mcp_json(tmp_path):
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {
        "a": {"command": "cmd", "args": ["/c", "npx", "-y", "pkg"]},
        "b": {"command": "python", "args": ["-m", "srv"], "optional": True},
    }}), encoding="utf-8")
    servers = mp.load_servers(cfg)
    assert set(servers) == {"a", "b"}


def test_missing_config_is_empty_not_a_crash(tmp_path):
    assert mp.load_servers(tmp_path / "nope.json") == {}


def test_corrupt_config_is_empty_not_a_crash(tmp_path):
    bad = tmp_path / ".mcp.json"
    bad.write_text("{not json", encoding="utf-8")
    assert mp.load_servers(bad) == {}


# ---- the cold-npx root cause ---------------------------------------------------

@pytest.mark.parametrize("args,expected", [
    (["/c", "npx", "-y", "pkg"], True),      # downloads on cold cache -> must warm
    (["/c", "uvx", "pkg"], True),
    (["-m", "server"], False),               # local, nothing to fetch
])
def test_network_launchers_are_detected_for_warming(args, expected):
    assert mp._needs_warm({"command": "cmd", "args": args}) is expected


# ---- the anti-hallucination rule -----------------------------------------------

def test_only_probed_up_tools_are_advertised():
    """An agent must be told what ACTUALLY responded, never what config claims."""
    report = {"servers": [
        {"name": "up", "status": "up", "tools": ["search", "fetch"]},
        {"name": "empty", "status": "no_tools", "tools": []},
        {"name": "dead", "status": "down", "tools": ["ghost"]},   # must NOT leak
    ]}
    assert mp.available_tools(report) == ["search", "fetch"]


# ---- failure classification (symptom -> cause -> fix) --------------------------

def test_missing_binary_is_not_a_retry_problem():
    row = {"name": "headroom", "status": "down",
           "stderr": "'.venv\\Scripts\\headroom.exe' is not recognized as an internal or external command"}
    c = mp.classify_failure(row)
    assert c["cause"] == "missing_binary"
    assert "Retrying cannot help" in c["fix"]


def test_missing_api_key_is_not_a_retry_problem():
    row = {"name": "brave-search", "status": "down",
           "stderr": "Error: --brave-api-key is required. You can get one at https://brave.com/search/api/"}
    c = mp.classify_failure(row)
    assert c["cause"] == "missing_credential"
    assert "Retrying cannot help" in c["fix"]


def test_timeout_is_classified_as_slow_not_broken():
    c = mp.classify_failure({"name": "ruflo", "status": "down", "error": "handshake_timeout"})
    assert c["cause"] == "slow_or_unresponsive"
    assert "TIMEOUT" in c["fix"].upper()


def test_connected_but_no_tools_is_down():
    c = mp.classify_failure({"name": "x", "status": "no_tools", "error": ""})
    assert c["cause"] == "connected_but_no_tools"


def test_remediation_lists_every_failure_with_a_fix():
    report = {"servers": [
        {"name": "ok", "status": "up", "tools": ["t"]},
        {"name": "bad", "status": "down", "stderr": "api-key is required", "optional": True},
    ]}
    fixes = mp.remediation(report)
    assert len(fixes) == 1 and fixes[0]["name"] == "bad"
    assert fixes[0]["optional"] is True


# ---- the gate ------------------------------------------------------------------

def test_required_server_down_blocks_optional_does_not(tmp_path, monkeypatch):
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {
        "req": {"command": "definitely-not-a-real-binary-xyz", "args": []},
        "opt": {"command": "definitely-not-a-real-binary-xyz", "args": [], "optional": True},
    }}), encoding="utf-8")
    monkeypatch.setenv("NEXI_MCP_RETRIES", "0")

    report = mp.preflight(cfg, warm=False, report_path=tmp_path / "report.json")

    assert report["ok"] is False
    assert "req" in report["blocked"], "a required server being down must block the task"
    assert "opt" in report["degraded"], "an optional server must degrade, not block"
    assert (tmp_path / "report.json").exists(), "report must be written for inspection"


def test_no_servers_configured_is_ok(tmp_path):
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    assert mp.preflight(cfg, warm=False, report_path=tmp_path / "r.json")["ok"] is True
