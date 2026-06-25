"""Optional local control API for CrewAI-style workflows (127.0.0.1:8127).

Import-guarded: FastAPI/uvicorn are NOT required to import this module (the engine and the
Nexi tools work without them). Run explicitly with:
    .venv\\Scripts\\python -m engine.integrations.crewai_style.web_server
Never started automatically by run.py. Thin layer over workflow_engine (single source of truth).
"""

from __future__ import annotations

from engine.integrations.crewai_style import workflow_engine as we

HOST = "127.0.0.1"
PORT = 8127

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    _AVAILABLE = True
except Exception:  # fastapi not installed — keep module importable
    _AVAILABLE = False


if _AVAILABLE:
    class _CreateBody(BaseModel):
        workflow_type: str
        input: str

    class _ContinueBody(BaseModel):
        user_input: str

    def create_app():
        app = FastAPI(title="Nexi CrewAI-style Workflow Server", version="0.1.0")

        def _run_or_404(run_id):
            run = we.get_run(run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return run

        @app.get("/health")
        def health():
            return {"ok": True, "service": "nexi-crewai-style-workflow-server"}

        @app.get("/workflows")
        def list_workflows():
            return [r.to_dict() for r in we.list_runs()]

        @app.post("/workflows")
        def create_workflow(body: _CreateBody):
            try:
                return we.create_run(body.workflow_type, body.input).to_dict()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.get("/workflows/{run_id}")
        def get_workflow(run_id: str):
            return _run_or_404(run_id).to_dict()

        @app.get("/workflows/{run_id}/events")
        def get_events(run_id: str):
            return _run_or_404(run_id).to_dict()["events"]

        @app.get("/workflows/{run_id}/logs")
        def get_logs(run_id: str):
            return {"run_id": run_id, "logs": _run_or_404(run_id).logs}

        @app.get("/workflows/{run_id}/artifacts")
        def get_artifacts(run_id: str):
            return {"run_id": run_id, "artifacts": _run_or_404(run_id).artifacts}

        @app.post("/workflows/{run_id}/continue")
        def continue_workflow(run_id: str, body: _ContinueBody):
            _run_or_404(run_id)
            return we.continue_run(run_id, body.user_input).to_dict()

        @app.post("/workflows/{run_id}/cancel")
        def cancel_workflow(run_id: str):
            _run_or_404(run_id)
            return we.cancel_run(run_id).to_dict()

        return app
else:
    def create_app():
        raise RuntimeError("Install fastapi + uvicorn to run the workflow server: pip install fastapi uvicorn")


def serve(host: str = HOST, port: int = PORT) -> None:
    import uvicorn
    uvicorn.run(create_app(), host=host, port=port, reload=False)


if __name__ == "__main__":
    serve()
