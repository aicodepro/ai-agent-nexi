# AGENTS.md — Nexi AI Assistant

## Repo Facts

- **Nexi** is a Windows desktop voice AI assistant: Python backends in `engine/`, Eel web UI in `www/`, wake/hotword/clap pipeline, brain/model routing, memory/context, and desktop control.
- This is a git repo on branch `jarvis-migration` (pre-existing user changes must remain untouched).
- No root README. Source of truth: `run.py`, `main.py`, `requirements.txt`, `.env.example`, `scripts/`, `tests/`, `engine/`.

## Setup & Commands

- Root is cwd; imports assume root on `sys.path`.
- Interpreter: `.venv\Scripts\python.exe` (Python 3.12.9).
- Install deps: `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- Full app: `.venv\Scripts\python.exe run.py` (UI + wake + scheduler).
- UI only: `.venv\Scripts\python.exe main.py` (Eel on port 8000).
- Object detection: `.venv\Scripts\python.exe app.py` (needs torch/YOLOv5).
- Syntax check: `.venv\Scripts\python.exe -m compileall engine`.
- Full test: `.venv\Scripts\python.exe -m pytest tests/ -v`.

## Architecture

- `engine/` is a PEP 420 namespace package (no `__init__.py`).
- `engine/audio_wake_pipeline.py` — main wake orchestration loop (1588 lines).
- `engine/command.py::allCommands` — Eel-exposed command dispatch.
- `engine/features.py::chatBot()` — core AI response via Gemini.
- `engine/brain/` — provider factory, model clients, provider registry.
- `engine/memory/` — context, local store, rules, redaction.
- `engine/runtime_bridge.py` — cross-process state sync.
- `www/` — old Eel UI (HTML/JS/CSS).
- `config/mcp.json` — MCP server definitions.
- Brain routing is **broken**: `provider_factory.py` always returns `MockModelClient`; real providers (Groq, OpenRouter) exist but are disconnected.

## Known Critical Issues (See NEXI_BUG_REGISTER.md)

- DSP clap speech-rejection logic accepts short speech as clap (false positives).
- Microphone disconnect silently kills pipeline (no detection, no recovery).
- Interrupt race: `clear_interrupt()` too early in `nexi_wake_controller.py`.
- Three disconnected model routing systems — brain always returns mock responses.
- Diverging `redact_sensitive()` in `memory_safety.py` vs `memory/memory_redaction.py`.
- `LocalMemoryStore` reads entire JSON file on every operation.
- `.mcp.json` filesystem/sqlite paths previously pointed to `E:/jarvis-main` (fixed 2026-07-24).
- `env` file (no dot) with live API keys must be gitignored and rotated.

## Safety Rules

- Do not read, print, or cache `.env` values.
- Never bypass `engine/control/safety.py` guards.
- Keep changes minimal and verified.
