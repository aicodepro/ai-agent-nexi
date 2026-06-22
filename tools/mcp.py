"""Minimal MCP (Model Context Protocol) stdio client.

Reads server definitions from config/mcp.json. Accepts the standard
"mcpServers" key (same as Claude Code / .mcp.json) or "servers":

    {"mcpServers": {"<name>": {"command": "npx", "args": ["-y", "some-mcp"], "env": {}}}}

Each call spawns the server, performs the JSON-RPC handshake over
newline-delimited stdio, runs one request, and shuts it down. Stateless and
simple — intended for occasional tool listing/calls, not high throughput.
"""

import json
import os
import subprocess
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "mcp.json"
_PROTOCOL = "2024-11-05"


def _load_servers() -> dict:
    try:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return cfg.get("mcpServers") or cfg.get("servers") or {}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _query(cfg: dict, method: str, params: dict):
    """Spawn a server, handshake, run one request, return its result dict."""
    env = {**os.environ, **cfg.get("env", {})}
    proc = subprocess.Popen(
        [cfg["command"], *cfg.get("args", [])],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv(target_id):
        for _ in range(50):  # bounded read to avoid hangs
            line = proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == target_id:
                return msg
        return None

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": _PROTOCOL, "capabilities": {},
                         "clientInfo": {"name": "nexi", "version": "1.0"}}})
        if recv(1) is None:
            return None
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
        msg = recv(2)
        return msg.get("result") if msg else None
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def list_tools() -> dict:
    """Return {server_name: [tool names]} across all configured servers."""
    out = {}
    for name, cfg in _load_servers().items():
        try:
            result = _query(cfg, "tools/list", {})
            tools = (result or {}).get("tools", [])
            out[name] = [t.get("name", "?") for t in tools]
        except Exception:
            out[name] = []
    return out


def call_tool(server: str, tool: str, arguments: dict = None) -> str:
    cfg = _load_servers().get(server)
    if not cfg:
        return f"No MCP server named '{server}'."
    result = _query(cfg, "tools/call", {"name": tool, "arguments": arguments or {}})
    if not result:
        return "No response from tool."
    parts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    return "\n".join(p for p in parts if p) or "Tool returned no text."
