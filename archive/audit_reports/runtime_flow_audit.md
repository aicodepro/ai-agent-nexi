# Runtime Flow Audit

## How `python run.py` Starts the System

```
run.py
├── load_dotenv()
├── install_clean_console_filter()
├── DemoMode check
├── Create multiprocessing.Queue (command_queue)
├── Create multiprocessing.Event (stop_event, audio_ready)
│
├── Process 1: startNexi() → main.main()
│   ├── Face recognition (optional)
│   ├── start_nexi()
│   │   ├── init_eel_ui(eel)           — sets up www/ or www_mark/ UI
│   │   ├── set_wake_queue(queue)       — bridge queue for audio process
│   │   ├── start_ui_bridge_pump()      — daemon thread consuming bridge events
│   │   ├── _find_free_port()
│   │   ├── _launch_edge_in_thread()    — opens Edge at http://localhost:8000
│   │   ├── eel.start('index.html', block=True)  — blocks forever
│   │
│   └── Eel-exposed functions:
│       ├── allCommands(message)        — legacy Eel entry point
│       ├── ui_submit_text(text)        — text submission
│       ├── ui_submit_file_drop()
│       ├── ui_get_env_status()
│       └── ...
│
├── Process 2: listenHotword()
│   ├── VOICE_WAKE_BACKEND=openwakeword → engine.audio_wake_pipeline
│   │   ├── start_audio_wake_pipeline(queue)
│   │   │   ├── mic open → audio frame queue
│   │   │   ├── wake detector thread (openWakeWord + clap)
│   │   │   ├── VAD command capture
│   │   │   ├── Groq Whisper ASR
│   │   │   ├── post_command(queue, text) — puts text on bridge queue
│   │   │   └── session lifecycle via wake_session_manager
│   │   └── is_pipeline_running() → signals audio_ready event
│   │
│   └── Legacy fallback: engine.features.hotword_no_key()
│       └── SpeechRecognition-based hotword → takecommand() → command_bus
│
├── Process 3: check_schedule (optional)
└── Process 4: check_alarm (optional)
```

## UI Process Bridge Pump

```
start_ui_bridge_pump(queue)
  └── Thread: _pump()
       └── queue.get(timeout=0.25) → handle_bridge_event(event)
            ├── EVENT_COMMAND_TEXT → submit_user_command(text, source, mode)
            │                         └── dispatch_unified_command(text, source)
            │                              └── allCommands(text)
            ├── EVENT_STATUS → _handle_status_event → emit_state()
            ├── EVENT_WAKE_DETECTED → emit_state("online")
            ├── EVENT_ASR_STARTED → emit_state("transcribing")
            ├── EVENT_ASR_RESULT → emit_state("transcribing")
            └── EVENT_ERROR → emit_state("error")
```

## Audio Process Pipeline Flow

```
audio_wake_pipeline.start_audio_wake_pipeline(queue)
  ├── Mic callback → AudioQueue (raw frames)
  ├── WakeDetector thread:
  │   ├── openWakeWord model → score > threshold + consecutive hits
  │   │   └── on_wake_detected()
  │   │       ├── start_session()
  │   │       ├── pause_detectors()
  │   │       ├── post_wake_detected(queue)
  │   │       ├── VAD command capture starts
  │   │       │   ├── wait_for_speech() → POST_WAKE_DELAY_MS (800ms)
  │   │       │   ├── buffer audio until end_silence (1800ms) or max_record (25s)
  │   │       │   ├── check VAD gates (speech_ms, duration_ms)
  │   │       │   ├── post_asr_started(queue)
  │   │       │   ├── Groq Whisper transcribe
  │   │       │   ├── post_command(queue, text) — sends to UI process
  │   │       │   └── finish_session() — on error/empty/timeout
  │   │       └── resume_detectors() — on session finish
  │   └── Clap detector (DSP / optional NN)
  └── Session lock prevents re-wake during active session
```

## State Machine Flow

```
SLEEPING → (wake_detected) → LISTENING → (speech_started) → RECORDING_UTTERANCE
  → (speech_ended) → RECOGNIZING → (asr_result) → THINKING → (tts_started) → SPEAKING
  → (tts_finished) → COOLDOWN → (cooldown_complete) → SLEEPING

Auto-followup shortcuts:
  SPEAKING → (question_detected) → mark_waiting_for_user() → auto_listen_requested=True
  → after speak_finished → _maybe_start_auto_followup() → takecommand() → submit_user_command()
```

## Key Files and Line Numbers

| Step | File | Function | Line |
|------|------|----------|------|
| Process spawn | `run.py` | `__main__` | 108-160 |
| UI start | `main.py` | `start_nexi()` | 223-262 |
| Bridge pump | `engine/runtime_bridge.py` | `start_ui_bridge_pump()` | 393-425 |
| Bridge event handler | `engine/runtime_bridge.py` | `handle_bridge_event()` | 179-263 |
| Wake pipeline start | `engine/audio_wake_pipeline.py` | `start_audio_wake_pipeline()` | ~500 |
| Command entry | `engine/command_bus.py` | `submit_user_command()` | 35-299 |
| Command dispatch | `engine/command_bus.py` | `dispatch_unified_command()` | 317-329 |
| Legacy command entry | `engine/command.py` | `allCommands()` | 1746-1963 |
| Router v2 entry | `engine/groq_intent_router_v2.py` | `route_intent_v2()` | 587-619 |
| Legacy router | `engine/intent_router.py` | `route_intent()` | 133-194 |
| Brain/Gemini | `engine/features.py` | `chatBot()` | 598-619 |
| TTS speak | `engine/command.py` | `speak()` | 277-369 |
| State machine | `engine/voice_state_machine.py` | `VoiceStateMachine.transition()` | 149-184 |
| Auto followup | `engine/command.py` | `_maybe_start_auto_followup()` | 502-525 |
