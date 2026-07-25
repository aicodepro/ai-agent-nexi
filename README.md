# Nexi — Neural Executive Intelligence

Nexi is a privacy-first desktop AI assistant for Windows. Wake detection runs
locally (no cloud until activated); cloud services (Gemini for Q&A, Groq for
ASR/TTS) are used only after an accepted wake event.

This is a clean, modular rebuild of the original Jarvis assistant — the
monolithic god-files were split into focused packages, the three intent routers
were unified, the four clap backends collapsed to one DSP backend, and the four
memory systems consolidated into a single manager.

## Features

- Local hotword wake detection ("Hey Nexi" / "Nexi")
- DSP-based double-clap wake detection (single-clap rejection)
- Silence / false-wake protection
- Unified intent routing (deterministic + LLM fallback)
- Gemini-powered multi-turn Q&A brain with memory context injection
- Groq Whisper ASR + Groq TTS (with pyttsx3 offline fallback)
- Desktop automation skills: apps, web, browser, files, system, clipboard, email
- Unified memory manager (preferences, conversation context, user model)
- Safety gate + emergency stop for risky actions
- Mark-style Eel desktop UI with live state visualisation

## Wake Flow

```text
SLEEP MODE
→ WAKE DETECTED
→ LISTENING
→ RECOGNISING
→ THINKING
→ SAYING
→ SLEEP MODE
```

Wake sources:

```text
1. Hotword: "Hey Nexi" / "Nexi"
2. Double clap
```

## Architecture

Dual-process, communicating over a `multiprocessing.Queue`:

```text
run.py                Launcher — spawns both processes
├── Process 1: UI + Command Engine (main.py → Eel @ :8000)
└── Process 2: Audio Wake Pipeline (wake/pipeline.py)
```

## Project Structure

```text
run.py            Dual-process launcher
main.py           UI process entry point (Eel-exposed API)
engine/           all runtime code (see below)
  command.py          command dispatch + speech I/O
  command_bus.py      single entry point for user input
  runtime_bridge.py   cross-process event bridge
  audio_wake_pipeline.py  mic -> wake -> VAD -> ASR
  wake_session_manager.py session/turn lifecycle
  ui_state_manager.py     ordered UI state events
  router_v3.py / groq_intent_router_v2.py  intent routing
  response_coordinator.py single response authority
  tool_registry.py        tool definitions + execution
  brain/, memory/, control/, integrations/, agent_runtime/
www_mark/         frontend (HTML/CSS/JS) - the active UI
prompts/          system prompt
config/, data/    runtime config & persisted state
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a local `.env` from `.env.example` and add your API keys
(`GEMINI_API_KEY`, `GROQ_API_KEY`). Never commit `.env`.

## Running Nexi

```powershell
python run.py
```

The UI opens automatically in Microsoft Edge app mode at
`http://localhost:8000/index.html`.

## Testing

Compile check:

```powershell
python -m compileall run.py main.py core intent brain memory skills control wake workflow ui
```

## Security Notes

Do not commit:

```text
.env
API keys / tokens
.venv/
models/  datasets/  artifacts/  logs/
*.pth  *.pt  *.onnx  *.wav  *.mp3
```

This repository should contain source code only.

## License

Private/internal project unless a license is explicitly added.
