"""MCP preflight: make every MCP server connect BEFORE any task runs.

Darsh's daily failure: "only 1-2 MCPs start, the rest fail — but when I reconnect
them manually they connect easily."

ROOT CAUSE (diagnosed from his .mcp.json): every server launches via `npx -y <pkg>`.
On a cold npm cache npx DOWNLOADS the package first — 10-60s — while the host's MCP
connect timeout is ~10s, so most servers time out on the first start. Manual reconnect
"works" only because npx cached the package on that first failed attempt. It was never
a flaky server; it was a cold cache racing a short timeout.

So this module does two things a plain retry cannot:
  1. WARM the launcher (npx package fetch) with a long timeout, once, before connecting.
  2. PROBE with tools/list — a server that connects but exposes ZERO tools is DOWN.
     That distinction matters: an agent told a server is "connected" when it exposes no
     tools will happily hallucinate calls to tools that do not exist.

Speaks MCP directly (JSON-RPC 2.0 over stdio, newline-delimited) — no SDK needed.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

_PROTOCOL_VERSION = "2024-11-05"


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def load_servers(config_path: str | Path | None = None) -> dict[str, dict]:
    """Read {name: spec} from an .mcp.json-style config."""
    path = Path(config_path or os.getenv("NEXI_MCP_CONFIG") or ".mcp.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[MCP_PREFLIGHT] config_unreadable reason={type(exc).__name__}", flush=True)
        return {}
    servers = data.get("mcpServers") or data.get("servers") or {}
    return {str(k): v for k, v in servers.items() if isinstance(v, dict)}


def _needs_warm(spec: dict) -> bool:
    """True when the launcher fetches from the network on first run (npx/uvx/bunx)."""
    blob = " ".join([str(spec.get("command") or "")] + [str(a) for a in (spec.get("args") or [])])
    return any(tok in blob for tok in ("npx", "uvx", "bunx", "pnpm dlx"))


def warm_launcher(name: str, spec: dict, timeout: float | None = None) -> dict:
    """Pre-fetch the package so the real connect isn't racing a download.

    Runs the server command with a LONG timeout and immediately kills it — we only
    need npm/uv to populate its cache. A timeout here is not a failure; the package
    may still have been (partially) cached, and connect() retries anyway.
    """
    if not _needs_warm(spec):
        return {"warmed": False, "reason": "no_network_launcher"}
    timeout = timeout if timeout is not None else _env_float("NEXI_MCP_WARM_TIMEOUT_S", 120.0)
    started = time.time()
    proc = None
    try:
        proc = subprocess.Popen(
            [str(spec.get("command"))] + [str(a) for a in (spec.get("args") or [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **{str(k): str(v) for k, v in (spec.get("env") or {}).items()}},
            cwd=spec.get("cwd") or None,
        )
        # Give the fetch time to complete; the server will start serving on stdio,
        # which is our signal the package is present.
        deadline = started + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                break             # exited (likely an error) — connect() will report it
            time.sleep(0.25)
            if time.time() - started > 2.0:
                break             # it's alive and serving => package is cached
        return {"warmed": True, "seconds": round(time.time() - started, 1)}
    except FileNotFoundError:
        return {"warmed": False, "reason": "command_not_found"}
    except Exception as exc:
        return {"warmed": False, "reason": type(exc).__name__}
    finally:
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


def probe_server(name: str, spec: dict, timeout: float | None = None) -> dict:
    """Start the server, do the MCP handshake, and count its tools.

    Returns {name, connected, tool_count, tools, status, error, seconds}.
    status: 'up' (connected AND tools>0) | 'no_tools' | 'down'
    """
    timeout = timeout if timeout is not None else _env_float("NEXI_MCP_CONNECT_TIMEOUT_S", 30.0)
    started = time.time()
    result = {"name": name, "connected": False, "tool_count": 0, "tools": [],
              "status": "down", "error": "", "seconds": 0.0}
    proc = None
    try:
        proc = subprocess.Popen(
            [str(spec.get("command"))] + [str(a) for a in (spec.get("args") or [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **{str(k): str(v) for k, v in (spec.get("env") or {}).items()}},
            cwd=spec.get("cwd") or None,
            # UTF-8 + replace, NOT text=True. On Windows text mode decodes with cp1252,
            # and any non-cp1252 byte a server emits (banners, box-drawing, WASM noise)
            # raises UnicodeDecodeError inside the reader thread. That killed the reader
            # instantly and the server was reported "handshake_timeout" — a FALSE
            # negative that condemned a server which was actually starting fine.
            text=True, bufsize=1, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        result["error"] = "command_not_found"
        result["seconds"] = round(time.time() - started, 1)
        return result
    except Exception as exc:
        result["error"] = type(exc).__name__
        result["seconds"] = round(time.time() - started, 1)
        return result

    reply: dict = {}
    done = threading.Event()

    def _read():
        """Collect JSON-RPC responses by id until we have the tools/list reply."""
        try:
            for line in proc.stdout:                      # newline-delimited JSON
                line = (line or "").strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if isinstance(msg, dict) and msg.get("id") is not None:
                    reply[msg["id"]] = msg
                    if msg.get("id") == 2:
                        done.set()
                        return
        except Exception:
            pass
        finally:
            done.set()

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()

    def _send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    try:
        _send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "nexi-mcp-preflight", "version": "1.0"},
        }})
        _send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        done.wait(timeout=timeout)

        if 1 in reply and "result" in reply[1]:
            result["connected"] = True
        tools_msg = reply.get(2) or {}
        tools = ((tools_msg.get("result") or {}).get("tools")) or []
        names = [str(t.get("name")) for t in tools if isinstance(t, dict) and t.get("name")]
        result["tool_count"] = len(names)
        result["tools"] = names[:50]

        # A successful tools/list IS proof of a working MCP session — that response can
        # only be produced by a server that completed the handshake. Requiring the
        # initialize reply to also be captured was too strict: some servers (ruv-swarm)
        # answer tools/list while their initialize reply is interleaved with banner
        # output, and the server was reported DOWN while advertising 25 usable tools.
        if result["tool_count"] > 0:
            result["connected"] = True
            result["status"] = "up"
        elif result["connected"]:
            # Connected but advertises nothing — treat as DOWN. Telling an agent this
            # server is available is how phantom-tool hallucinations start.
            result["status"] = "no_tools"
        else:
            result["error"] = result["error"] or "handshake_timeout"
    except Exception as exc:
        result["error"] = type(exc).__name__
    finally:
        # On failure the REAL reason is almost always on stderr ("BRAVE_API_KEY not set",
        # "command not found", a stack trace). Without this a user only sees
        # "handshake_timeout", which is a symptom, not a cause — and cannot fix it.
        if result["status"] != "up":
            try:
                if proc.poll() is None:
                    proc.kill()
                _, err = proc.communicate(timeout=5)
                tail = " | ".join(
                    ln.strip() for ln in str(err or "").splitlines() if ln.strip()
                )[-400:]
                if tail:
                    result["stderr"] = tail
                    result["error"] = f"{result['error']}: {tail[:160]}" if result["error"] else tail[:160]
            except Exception:
                pass
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        result["seconds"] = round(time.time() - started, 1)
    return result


def preflight(config_path: str | Path | None = None, *, warm: bool = True,
              retries: int | None = None, parallel: bool = True,
              report_path: str | Path | None = None) -> dict:
    """Connect + probe every configured MCP server before any task runs.

    A server marked optional in the config may fail without blocking; a REQUIRED
    server that is down blocks the task. Returns a structured report and writes it to
    artifacts/mcp_preflight.json so the failure is inspectable after the fact.
    """
    servers = load_servers(config_path)
    if not servers:
        return {"ok": True, "servers": [], "blocked": [], "degraded": [],
                "message": "No MCP servers configured."}

    retries = retries if retries is not None else _env_int("NEXI_MCP_RETRIES", 3)
    results: dict[str, dict] = {}

    def _one(name: str, spec: dict):
        if warm:
            spec_warm = warm_launcher(name, spec)
        else:
            spec_warm = {"warmed": False, "reason": "disabled"}
        attempt = 0
        res = {}
        while attempt <= retries:
            res = probe_server(name, spec)
            if res["status"] == "up":
                break
            attempt += 1
            if attempt <= retries:
                time.sleep(min(2 ** (attempt - 1), 8))   # 1s, 2s, 4s, 8s
        res["attempts"] = attempt + 1
        res["warm"] = spec_warm
        res["optional"] = bool(spec.get("optional", False))
        results[name] = res
        flag = "OK " if res["status"] == "up" else "FAIL"
        print(f"[MCP_PREFLIGHT] {flag} {name} status={res['status']} "
              f"tools={res['tool_count']} attempts={res['attempts']} {res['seconds']}s", flush=True)

    if parallel:
        threads = [threading.Thread(target=_one, args=(n, s), daemon=True)
                   for n, s in servers.items()]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=_env_float("NEXI_MCP_TOTAL_TIMEOUT_S", 300.0))
    else:
        for n, s in servers.items():
            _one(n, s)

    rows = [results.get(n, {"name": n, "status": "down", "optional": bool(s.get("optional", False)),
                            "tool_count": 0, "error": "not_probed"})
            for n, s in servers.items()]
    blocked = [r["name"] for r in rows if r["status"] != "up" and not r.get("optional")]
    degraded = [r["name"] for r in rows if r["status"] != "up" and r.get("optional")]
    total_tools = sum(int(r.get("tool_count", 0)) for r in rows)

    report = {
        "ok": not blocked,
        "servers": rows,
        "blocked": blocked,
        "degraded": degraded,
        "total_tools": total_tools,
        "message": ("All required MCP servers are up."
                    if not blocked else
                    f"Required MCP servers down: {', '.join(blocked)}"),
    }

    out = Path(report_path or os.getenv("NEXI_MCP_REPORT") or "artifacts/mcp_preflight.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report


def classify_failure(row: dict) -> dict:
    """Turn a raw failure into a CAUSE and a concrete FIX.

    'handshake_timeout' is a symptom, not a cause — a user can't act on it. Reading the
    server's own stderr tells you whether it's a missing binary, a missing key, or a
    genuinely slow start, and each has a different fix. Retrying forever fixes none of
    the first two: a server demanding an API key will never connect, no matter what.
    """
    blob = f"{row.get('stderr', '')} {row.get('error', '')}".lower()
    name = row.get("name", "")
    if "is not recognized" in blob or "command_not_found" in blob or "no such file" in blob:
        return {"cause": "missing_binary", "fixable": "config",
                "fix": f"'{name}' points at a program that does not exist. Install it, or "
                       f"remove the entry from .mcp.json. Retrying cannot help."}
    if "api-key" in blob or "api key" in blob or "unauthorized" in blob or "401" in blob:
        return {"cause": "missing_credential", "fixable": "config",
                "fix": f"'{name}' requires an API key. Set it in the server's env block, or "
                       f"replace it with a key-free alternative. Retrying cannot help."}
    if "handshake_timeout" in blob or "timeout" in blob:
        return {"cause": "slow_or_unresponsive", "fixable": "timeout",
                "fix": f"'{name}' started but did not complete the MCP handshake. Raise "
                       f"NEXI_MCP_CONNECT_TIMEOUT_S, or verify it actually speaks MCP over stdio."}
    if row.get("status") == "no_tools":
        return {"cause": "connected_but_no_tools", "fixable": "server",
                "fix": f"'{name}' connected but advertises zero tools — treated as DOWN so no "
                       f"agent is told a phantom capability exists."}
    return {"cause": "unknown", "fixable": "investigate",
            "fix": f"See stderr for '{name}' in artifacts/mcp_preflight.json."}


def remediation(report: dict) -> list[dict]:
    """Actionable fix list for everything that isn't up."""
    out = []
    for row in report.get("servers", []):
        if row.get("status") != "up":
            item = classify_failure(row)
            item["name"] = row.get("name")
            item["optional"] = row.get("optional", False)
            out.append(item)
    return out


def available_tools(report: dict) -> list[str]:
    """Flat list of tools that ACTUALLY responded — this is what an agent should be
    told it has. Never derive capability from the config file; derive it from a probe."""
    out: list[str] = []
    for row in report.get("servers", []):
        if row.get("status") == "up":
            out.extend(row.get("tools") or [])
    return out


def _demo() -> None:
    # pure-logic checks that run without spawning anything
    assert _needs_warm({"command": "cmd", "args": ["/c", "npx", "-y", "pkg"]})
    assert not _needs_warm({"command": "python", "args": ["-m", "server"]})
    rep = {"servers": [
        {"name": "a", "status": "up", "tools": ["t1", "t2"]},
        {"name": "b", "status": "no_tools", "tools": []},
    ]}
    assert available_tools(rep) == ["t1", "t2"], "only probed-up tools may be advertised"
    print("mcp_preflight._demo OK")


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        _demo()
    else:
        r = preflight()
        print(json.dumps({k: v for k, v in r.items() if k != "servers"}, indent=2))
        raise SystemExit(0 if r["ok"] else 1)
