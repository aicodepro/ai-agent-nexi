"""Optional local control API for CrewAI-style workflows (127.0.0.1:8127).

Stdlib http.server only — NO third-party dependency (ponytail: stdlib over a new dep, so it
runs out of the box). Thin layer over workflow_engine (single source of truth). Never started
automatically by run.py. Run explicitly with:
    .venv\\Scripts\\python -m engine.integrations.crewai_style.web_server

Routing logic is the pure `route()` function so it's testable without binding a port.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from engine.integrations.crewai_style import workflow_engine as we

HOST = "127.0.0.1"
PORT = 8127
_ALLOWED = ("router_audit", "codebase_research", "test_generation", "integration_plan")


def route(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """Pure request router → (status, json-able). Used by the HTTP handler and tests."""
    body = body or {}
    parts = [p for p in path.strip("/").split("/") if p]

    if method == "GET" and path == "/health":
        return 200, {"ok": True, "service": "nexi-crewai-style-workflow-server"}
    if method == "GET" and parts == ["workflows"]:
        return 200, [r.to_dict() for r in we.list_runs()]
    if method == "POST" and parts == ["workflows"]:
        if body.get("workflow_type") not in _ALLOWED:
            return 400, {"error": f"workflow_type must be one of {list(_ALLOWED)}"}
        return 200, we.create_run(body["workflow_type"], body.get("input", "")).to_dict()

    if parts and parts[0] == "workflows" and len(parts) >= 2:
        run = we.get_run(parts[1])
        if run is None:
            return 404, {"error": "Workflow not found"}
        sub = parts[2] if len(parts) > 2 else None
        if method == "GET" and sub is None:
            return 200, run.to_dict()
        if method == "GET" and sub == "events":
            return 200, run.to_dict()["events"]
        if method == "GET" and sub == "logs":
            return 200, {"run_id": run.run_id, "logs": run.logs}
        if method == "GET" and sub == "artifacts":
            return 200, {"run_id": run.run_id, "artifacts": run.artifacts}
        if method == "POST" and sub == "continue":
            return 200, we.continue_run(run.run_id, body.get("user_input", "")).to_dict()
        if method == "POST" and sub == "cancel":
            return 200, we.cancel_run(run.run_id).to_dict()

    return 404, {"error": "Not found"}


class _Handler(BaseHTTPRequestHandler):
    def _dispatch(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        status, payload = route(method, self.path, body)
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, *_a):  # quiet
        pass


def serve(host: str = HOST, port: int = PORT) -> None:
    print(f"[CREWAI] workflow server on http://{host}:{port}", flush=True)
    HTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    serve()
