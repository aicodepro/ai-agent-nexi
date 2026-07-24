# Nexi AI Assistant — Project Guidelines

## Repo
- Windows desktop voice AI assistant (Python + Eel web UI)
- Branch: `jarvis-migration`
- Interpreter: `.venv\Scripts\python.exe`
- Root is always cwd; `engine/` is a PEP 420 namespace package

## Commands
- Run full app: `.venv\Scripts\python.exe run.py`
- Run tests: `.venv\Scripts\python.exe -m pytest tests/ -v`
- Syntax check: `.venv\Scripts\python.exe -m compileall engine`
- Install deps: `.venv\Scripts\python.exe -m pip install -r requirements.txt`

## Critical Context
- Brain always returns mock responses (three disconnected routing systems)
- DSP clap has false positive issue (short speech accepted as clap)
- Mic disconnect is undetected (no recovery mechanism)
- See `NEXI_BUG_REGISTER.md` for full bug inventory
- See `AGENTS.md` for architecture details
