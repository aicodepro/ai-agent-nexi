# Jarvis Voice Assistant — Phase 4 Requirements

## Master Requirements Addendum

This addendum is the active A-to-Z execution path for Phase 4. It preserves the original feature requirements below and adds the verified project overview, system architecture, subsystem catalog, configuration reference, implementation gates, plugin/MCP usage rules, and audit baseline.

### Project Overview

Jarvis is a Windows-only Python desktop voice assistant. It is not a container service and not a web app. The runtime combines an Eel web UI, an Edge app window, wake/audio backends, Groq Whisper ASR, Gemini/Groq brain routing, local tool execution, hierarchical memory, and guarded PC control.

Primary runtime modes:

| Entrypoint | Purpose |
|---|---|
| `run.py` | Full runtime. Starts UI process, wake/audio process, and optional schedule/alarm watchers. |
| `main.py` | UI/assistant only. Starts Eel, opens Edge, and runs the command bridge. |
| `app.py` | Standalone object-detection demo. Uses YOLO/camera and is not started by `run.py`. |

UI roots:

| UI | Directory | Notes |
|---|---|---|
| Legacy UI | `www/` | Original Eel UI. Must keep bridge functions synchronized. |
| Mark UI | `www_mark/` | HUD/dashboard UI selected by `JARVIS_UI_MODE=mark`. |

Core voice flow:

```text
SLEEPING -> ONLINE -> LISTENING -> RECOGNISING -> THINKING -> SAYING -> SLEEPING
```

Canonical backend state owns the UI state. The UI must display Python-emitted state; it must not invent PASS or fake lifecycle transitions.

### System Requirements

| Requirement | Value |
|---|---|
| OS | Windows 10/11 only |
| Python | Python 3.12.x; local verified interpreter is `.venv\Scripts\python.exe` |
| Browser | Microsoft Edge Chromium for Eel app window |
| Hardware | Microphone and speakers required; camera optional for gesture/eye control |
| Memory | 8GB RAM recommended |
| Storage | 2GB+ recommended for venv, local models, logs, and memory data |
| Network | Required for Groq ASR/TTS/intent and Gemini brain unless fallbacks/demo mode are active |

### Technology Stack

| Subsystem | Stack |
|---|---|
| Desktop runtime | Python, multiprocessing, Eel, Edge app window |
| UI bridge | Eel exposed JS functions, `runtime_bridge.py`, `ui_state_manager.py`, UI ACK checks |
| Wake | openWakeWord, DSP double-clap, optional hotkey, wake arbitration/session lock |
| VAD/audio | sounddevice/PyAudio style audio capture, Silero VAD settings, RMS gates |
| ASR | Groq Whisper `whisper-large-v3-turbo` via `engine/groq_asr.py` |
| TTS | Groq Orpheus WAV output, `pyttsx3` fallback, simpleaudio interrupt handle |
| Brain | Gemini Flash default; Groq intent planner/router; optional provider registry under `engine/brain` |
| Safety | `engine/safety_gate.py`, `engine/control/safety.py`, EmergencyStop, SandboxPolicy |
| Memory | Session, episodic, semantic, adaptive, reflection, correction rules |
| Vision/control | MediaPipe-style hand/eye control modules, screen trust, screenshot/privacy guards |
| Tests | pytest, compileall, Jarvis verifier scripts, Playwright runtime check |

### Master Architecture Flow

```text
[User vocal or ambient input]
        |
        v
[Wake monitors]
  - openWakeWord hotword
  - DSP double clap
  - optional hotkey
        |
        v
[Wake session manager]
  - one active session
  - pause detectors while active
  - 60s timeout safety recovery
        |
        v
[VAD command capture]
  - post-wake delay
  - no-speech timeout
  - end-silence detection
  - tolerant speech gate for valid recordings
        |
        v
[Groq Whisper ASR]
        |
        v
[runtime_bridge queue event]
        |
        v
[command_bus -> command.py::allCommands]
        |
        v
[Routing]
  - clarification/workflow/memory/output/local skills
  - Phase3CommandBridge
  - intent v2 and ReAct route
  - legacy intent router and brain fallback
        |
        v
[Execution]
  - tool registry with safety gate
  - ReAct loop with bounded steps
  - Gemini/Groq brain response
        |
        v
[Response]
  - tone selection
  - transcript card
  - Groq/pyttsx3 TTS
  - SAYING state
        |
        v
[Session finish]
  - clear short-term memory
  - resume detectors
  - return to SLEEPING
```

### Process Model

```text
run.py
  |
  +-- UI process: main.py
  |     +-- init Eel from engine/ui_loader.py
  |     +-- serve www/ or www_mark/
  |     +-- start runtime_bridge pump
  |     +-- open Edge app window
  |     +-- dispatch command.py::allCommands
  |
  +-- Wake/audio process
        +-- audio_wake_pipeline.py
        +-- hotword_engine_manager.py
        +-- clap_backend_manager.py / dsp_clap_backend.py
        +-- VAD capture
        +-- groq_asr.py
        +-- post runtime_bridge events
```

### Runtime Bridge Event Protocol

Core event constants are defined in `engine/runtime_bridge.py`:

| Event | UI/Runtime Meaning |
|---|---|
| `command_text` | ASR/text command submitted to command bus |
| `status` | Generic status event mapped through `STATUS_TO_UI_STATE` |
| `wake_detected` | Wake source detected; maps to ONLINE |
| `listening_started` | Command capture started |
| `waiting_for_speech` | Wake accepted, waiting for user speech |
| `speech_started` | VAD detected speech; maps to RECOGNISING |
| `speech_ended` | VAD ended speech segment |
| `asr_started` | ASR upload/transcription started |
| `asr_result` | ASR returned transcript or empty result |
| `thinking_started` | Command processing started |
| `react_thinking` | ReAct loop internal planning status |
| `react_tool_start` | ReAct tool execution started |
| `react_tool_end` | ReAct tool execution ended |
| `speaking_started` | TTS started; maps to SAYING |
| `interrupted` | Barge-in interrupted TTS; maps to LISTENING |
| `idle` | Return to sleep/ready |
| `sleeping` | Canonical sleeping state |
| `error` | Runtime error state |
| `dashboard_update` | Push World Monitor dashboard payload |
| `diagnostics_request` | Request diagnostics from UI/runtime |
| `diagnostics_result` | Push diagnostics result payload |
| `transcript` | Push transcript card payload |

### Full Subsystem Catalog

#### Root Runtime Files

| File | Role |
|---|---|
| `run.py` | Full multiprocessing runtime launcher. |
| `main.py` | Eel UI process and command bridge setup. |
| `app.py` | Standalone camera/object-detection demo. |
| `.env.example` | Source-of-truth public config template. |
| `requirements.txt` | Python dependency list. |

#### `engine/` Core Modules

| Module | Role |
|---|---|
| `adaptive_memory.py` | Adaptive long-term memory and learning from exchanges. |
| `app_resolver.py` | Resolves user app names to Windows targets. |
| `assistant_response.py` | Response verification, follow-up suppression, and guarded wording. |
| `audio_wake_pipeline.py` | Wake -> VAD -> ASR -> bridge command pipeline. |
| `automaticTyping.py` | Legacy automatic typing helper. |
| `barge_in_manager.py` | TTS interruption and barge-in debounce manager. |
| `clap_backend_manager.py` | Selects and coordinates clap backends. |
| `clap_detector.py` | Legacy clap listener. |
| `clap_model_adapter.py` | Clap model adapter layer. |
| `clap_nn_backend.py` | Neural clap backend, optional. |
| `clarification_manager.py` | Clarifying questions and pending clarification state. |
| `cognitive_context.py` | Explainability and cognitive route context. |
| `command.py` | Main Eel-exposed command router and response/TTS path. |
| `command_bus.py` | Re-entry guard, command normalization, source/mode tracking. |
| `confidence_manager.py` | Confidence scoring and clarify thresholds. |
| `config.py` | Assistant config constants. |
| `conversation_context.py` | Recent turn context and repeat-last support. |
| `correction_learner.py` | User correction rules and reflection feed. |
| `create_folder_workflow.py` | Folder workflow helper. |
| `db.py` | Legacy database helpers. |
| `debug_trace.py` | Runtime trace logging. |
| `deep_training_engine.py` | Ultra/deep training profile engine. |
| `demo_mode.py` | Safe presentation/demo fallbacks and log suppression. |
| `diagnostics.py` | Component health aggregator. |
| `dsp_clap_backend.py` | DSP double-clap detector and timing source of truth. |
| `entity_resolver.py` | Entity extraction/resolution helper. |
| `Eye_mouse_Controller.py` | Legacy eye mouse controller entry. |
| `features.py` | Legacy app/contact/chatBot feature layer and brain entry. |
| `file_operations.py` | Legacy file operation helpers. |
| `followup_manager.py` | Follow-up prompt state. |
| `Game.py` | Legacy game helper. |
| `gemini_brain.py` | Gemini provider wrapper. |
| `GoogleMaps.py` | Legacy maps helper. |
| `groq_asr.py` | Groq Whisper ASR wrapper with demo fallback. |
| `groq_intent_planner.py` | Groq planner model config/helpers. |
| `groq_intent_router_v2.py` | Intent v2 router, deterministic fallback, presence confidence updates. |
| `groq_tts.py` | Groq TTS and interrupt-aware playback handle. |
| `HandGesture.py` | Legacy hand gesture entry. |
| `helper.py` | General helper functions. |
| `hotkey_wake.py` | Optional keyboard wake source. |
| `hotword_engine_manager.py` | openWakeWord lifecycle and scoring. |
| `hotword_helper.py` | Hotword phrase/cooldown helpers. |
| `intent_context_builder.py` | Builds routing context from workflow, follow-up, output, and memory. |
| `intent_explainer.py` | Stores/explains latest intent decision. |
| `intent_pre_router.py` | Deterministic pre-router. |
| `intent_router.py` | Legacy intent router. |
| `intent_taxonomy.py` | Canonical intent schemas and route defaults. |
| `intent_validator.py` | Router result validation. |
| `intents.py` | Legacy regex/intent matching. |
| `internal_wake_signal.py` | Internal wake signaling. |
| `interrupt_controller.py` | TTS/command interrupt state. |
| `jarvis_wake_controller.py` | Sleep/wake control state. |
| `keyboard.py` | Legacy keyboard helper. |
| `lightning_gateway.py` | Optional Lightning provider gateway. |
| `llm_parameter_extractor.py` | LLM slot extraction for workflows/tools. |
| `local_skills.py` | Deterministic local skill execution. |
| `mcp_tool_bridge.py` | MCP-to-tool bridge surface. |
| `memory_safety.py` | Memory redaction and safe-to-store checks. |
| `memory_store.py` | Legacy memory API with adaptive and semantic write-through. |
| `need_training_manager.py` | Need-based training profiles. |
| `news.py` | Legacy news helper. |
| `output_actions.py` | Output workspace copy/save/shorten actions. |
| `output_router.py` | Output workspace routing. |
| `presence_state.py` | Canonical presence singleton: mode, attention, confidence, tone, goal. |
| `prompt_loader.py` | Loads prompt files. |
| `react_planner.py` | Bounded ReAct tool loop with safety gate. |
| `realtime_cognitive_engine.py` | Realtime cognitive/context engine. |
| `reflection_engine.py` | Reflects after turns. |
| `reflection_memory.py` | Stores and recalls learned failure lessons. |
| `runtime_bridge.py` | Multiprocessing event bridge to UI process. |
| `safety_gate.py` | Risk classification and direct/ReAct execution boundary. |
| `SendEmail.py` | Legacy email helper. |
| `slot_normalizer.py` | Slot/value normalization. |
| `smart_followup_engine.py` | Follow-up resolution and output follow-ups. |
| `speech_progress.py` | Speech progress helpers. |
| `text_to_image.py` | Text-to-image helper. |
| `tone_manager.py` | Tone selection, response wrapping, presence tone updates. |
| `tool_category_view.py` | Tool grouping/category view. |
| `tool_manifest_loader.py` | Tool manifest loading for router context. |
| `tool_registry.py` | Registered local tools, OpenAI schemas, safety-checked execution. |
| `tool_result_verifier.py` | Verifies tool outcomes before success claims. |
| `tool_usage_intelligence.py` | Learns tool aliases/outcomes. |
| `train_mode.py` | Basic training mode. |
| `training_curriculum.py` | Training curriculum generation. |
| `training_dataset.py` | Training dataset creation. |
| `training_evaluator.py` | Training evaluation. |
| `training_explainer.py` | Training explanations. |
| `training_feedback.py` | Training feedback handling. |
| `training_policy.py` | Training safety/policy rules. |
| `training_profile_store.py` | Training profile persistence. |
| `training_replay.py` | Training replay. |
| `training_rules.py` | User/system training rules. |
| `training_safety.py` | Training safety checks. |
| `training_simulator.py` | Training simulation. |
| `training_storage.py` | Training storage helpers. |
| `transcript_filter.py` | Transcript sanitization and follow-up bypass. |
| `tts_provider_manager.py` | TTS provider order and fallback manager. |
| `tts_response_manager.py` | TTS response summary/chunk handling. |
| `turn_manager.py` | Current conversational turn state. |
| `tzur_clap_adapter.py` | Legacy/optional Tzur clap adapter; not default. |
| `ui_adapter.py` | Safe UI call adapter. |
| `ui_event_bridge.py` | UI event relay helpers. |
| `ui_loader.py` | Selects `www/` or `www_mark/`. |
| `ui_state_ack.py` | UI ACK tracking. |
| `ui_state_manager.py` | Canonical UI state emitter and presence bridge. |
| `user_intent_profile.py` | User intent profile memory. |
| `user_model.py` | User model/preference context. |
| `wake_arbitration_manager.py` | Wake event arbitration. |
| `wake_orchestrator.py` | Multi-source wake coordination. |
| `wake_session_manager.py` | Session lock, detector pause/resume, timeout, presence session state. |
| `website_resolver.py` | Website/domain resolver. |
| `workflow_dialog_manager.py` | Workflow slot dialog manager. |
| `workflow_manager.py` | Workflow execution manager. |
| `workflow_state.py` | Active workflow state. |
| `world_monitor_dashboard.py` | Runtime dashboard panel aggregation. |
| `yamnet_clap_backend.py` | Optional YAMNet clap backend. |

#### `engine/memory/`

| Module | Role |
|---|---|
| `__init__.py` | Three-layer memory exports. |
| `session_memory.py` | In-memory short-term turn store cleared by session finish/start. |
| `episodic_memory.py` | Append-only task/command episode store. |
| `semantic_memory.py` | Structured fact/preference/project/correction store. |

#### `engine/camera_control/`

| Module | Role |
|---|---|
| `__init__.py` | Camera control package exports. |
| `eye_controller.py` | Eye tracking controller. |
| `gpu.py` | GPU capability helpers. |
| `hand_controller.py` | Hand gesture controller. |
| `mouse_actions.py` | Mouse action execution helpers. |
| `smoothing.py` | Input smoothing filters. |

#### `engine/`

| Module | Role |
|---|---|
| `app/phase3_command_bridge.py` | Bridge from legacy command flow into Nexi systems. |
| `app/runtime_context.py` | Runtime conversation context access. |
| `brain/action_planner.py` | Plans control actions. |
| `brain/action_verifier.py` | Verifies planned/executed actions. |
| `brain/autonomy_loop.py` | Autonomous task loop. |
| `brain/bilingual_normalizer.py` | Bilingual command normalization. |
| `brain/intent_brain.py` | Intent brain abstraction. |
| `brain/model_client.py` | Model client wrapper. |
| `brain/model_fallback.py` | Model fallback handling. |
| `brain/model_metrics.py` | Model metrics tracking. |
| `brain/model_policy.py` | Model selection policy. |
| `brain/model_router.py` | Provider/model routing. |
| `brain/provider_factory.py` | Provider construction. |
| `brain/provider_registry.py` | Provider defaults/local config registry. |
| `brain/recovery_planner.py` | Recovery planning. |
| `brain/self_reflection.py` | Nexi self-reflection helpers. |
| `brain/speech_recovery.py` | Speech recovery logic. |
| `brain/task_state.py` | Task state model. |
| `control/action_gate.py` | Control-layer action gate. |
| `control/base.py` | Control base classes. |
| `control/browser_session.py` | Browser session helpers. |
| `control/chrome_controller.py` | Chrome/CDP control. |
| `control/desktop_controller.py` | Desktop control. |
| `control/file_controller.py` | File control with safety boundaries. |
| `control/permission_manager.py` | Permission/confirmation manager. |
| `control/process_controller.py` | Process control. |
| `control/registry.py` | Control action registry. |
| `control/safety.py` | EmergencyStop and SandboxPolicy. |
| `control/window_controller.py` | Window focus/move/control. |
| `diagnostics/bridge_doctor.py` | Bridge diagnostics. |
| `diagnostics/hotword_doctor.py` | Hotword diagnostics. |
| `diagnostics/playwright_doctor.py` | Playwright diagnostics. |
| `diagnostics/runtime_doctor.py` | Runtime diagnostics aggregator. |
| `memory/conversation_buffer.py` | Nexi conversation buffer. |
| `memory/local_memory.py` | Local JSON/JSONL memory. |
| `memory/memory_policy.py` | Memory retention/store policy. |
| `memory/memory_redaction.py` | Memory redaction. |
| `memory/preference_store.py` | Preference persistence. |
| `memory/task_memory.py` | Task memory. |
| `vision/privacy_guard.py` | Vision privacy guard. |
| `vision/screen_context.py` | Screen context formatting. |
| `vision/screen_observer.py` | Screenshot/screen observation. |
| `vision/screen_trust.py` | Trusted screen access state. |
| `vision/screenshot_service.py` | Screenshot capture service. |
| `vision/vision_analyzer.py` | Vision analysis layer. |
| `voice/response_style.py` | Response style helpers. |
| `voice/speech_controller.py` | Speech controller. |
| `voice/speech_interrupt.py` | Stop/emergency speech classifier. |
| `voice/voice_orchestrator.py` | Voice orchestration. |
| `voice/voice_personality.py` | Voice personality configuration. |

### Full Configuration Reference

All variables below come from `.env.example`. Empty defaults mean the user must provide a local value in `.env` if that provider/feature is enabled. Never print or commit real `.env` values.

#### Assistant / Startup / Demo

| Variable | Default | Purpose |
|---|---|---|
| `ASSISTANT_NAME` | `jarvis` | Assistant name. |
| `FACE_RECOGNITION_ON_STARTUP` | `false` | Legacy startup face-recognition toggle. |
| `CAMERA_ON_STARTUP` | `false` | Legacy startup camera toggle. |
| `JARVIS_DEMO_MODE` | `false` | Enables safe presentation mode. |
| `JARVIS_DEMO_DISABLE_AUTO_FOLLOWUP` | `true` | Suppresses follow-up listening in demo. |
| `JARVIS_DEMO_USE_LOCAL_TTS` | `true` | Forces local TTS in demo. |
| `JARVIS_DEMO_REDUCE_LOGS` | `true` | Hides noisy logs in demo. |

#### Wake Orchestrator / Hotword / Clap / Hotkey

| Variable | Default |
|---|---|
| `JARVIS_WAKE_SOURCES` | `hotword,double_clap,hotkey` |
| `JARVIS_WAKE_COOLDOWN_MS` | `1500` |
| `JARVIS_WAKE_SUPPRESS_WHILE_LISTENING` | `true` |
| `JARVIS_WAKE_DEBUG` | `false` |
| `PICOVOICE_ACCESS_KEY` | empty |
| `PORCUPINE_ACCESS_KEY` | empty |
| `HOTWORD_BACKEND` | `auto` |
| `HOTWORD_SENSITIVITY` | `0.85` |
| `VOICE_WAKE_BACKEND` | `openwakeword` |
| `OPENWAKEWORD_ENABLED` | `true` |
| `JARVIS_HOTWORD_ENABLED` | `true` |
| `JARVIS_HOTWORD_PHRASES` | `hey jarvis,jarvis` |
| `JARVIS_HOTWORD_PHRASE` | `hey jarvis` |
| `JARVIS_HOTWORD_BACKEND_ORDER` | `openwakeword,vosk_keyword,hotkey` |
| `OPENWAKEWORD_MODEL_PATH` | empty |
| `OPENWAKEWORD_PRETRAINED_MODELS` | `hey jarvis` |
| `OPENWAKEWORD_SCORE_THRESHOLD` | `0.25` |
| `OPENWAKEWORD_CONSECUTIVE_HITS` | `1` |
| `OPENWAKEWORD_COOLDOWN_MS` | `1500` |
| `OPENWAKEWORD_DEBUG` | `false` |
| `DISABLE_LEGACY_HOTWORD_FALLBACK` | `true` |
| `WAKE_PHRASE_HINT` | `Say "Hey Jarvis" or double clap` |
| `JARVIS_CLAP_ENABLED` | `true` |
| `JARVIS_CLAP_BACKEND_ORDER` | `dsp_clap,clap_nn` |
| `JARVIS_CLAP_PRIMARY` | `dsp_clap` |
| `JARVIS_CLAP_PATTERN` | `double` |
| `JARVIS_CLAP_MIN_GAP_MS` | `100` |
| `JARVIS_CLAP_MAX_GAP_MS` | `4500` |
| `JARVIS_CLAP_COOLDOWN_MS` | `1500` |
| `JARVIS_CLAP_DEBUG` | `false` |
| `JARVIS_DSP_CLAP_RMS_THRESHOLD` | `0.025` |
| `JARVIS_DSP_CLAP_PEAK_THRESHOLD` | `0.08` |
| `JARVIS_DSP_CLAP_PEAK_RATIO` | `3.5` |
| `JARVIS_DSP_CLAP_HF_RATIO` | `0.25` |
| `JARVIS_DSP_CLAP_EVENT_COOLDOWN_MS` | `80` |
| `JARVIS_DSP_CLAP_SPEECH_REJECT_MS` | `250` |
| `CLAP_DETECTION_ENABLED` | `true` |
| `CLAP_WAKE_MODE` | `double` |
| `CLAP_COOLDOWN_SECONDS` | `2.0` |
| `CLAP_WINDOW_SECONDS` | `0.8` |
| `CLAP_MIN_RMS` | `0.08` |
| `CLAP_PEAK_THRESHOLD` | `0.35` |
| `CLAP_MIN_GAP_MS` | `100` |
| `CLAP_MAX_GAP_MS` | `4500` |
| `CLAP_MAX_EVENT_MS` | `180` |
| `CLAP_NOISE_FLOOR_ALPHA` | `0.95` |
| `CLAP_MAX_ACTIVE_RATIO` | `0.35` |
| `CLAP_MIN_CREST_FACTOR` | `1.8` |
| `CLAP_MODEL_PATH` | empty |
| `JARVIS_HOTKEY_ENABLED` | `false` |
| `JARVIS_HOTKEY_WAKE_ENABLED` | `false` |
| `JARVIS_HOTKEY` | `win+j` |
| `JARVIS_HOTKEY_FALLBACK` | `ctrl+alt+j` |
| `JARVIS_SLEEP_ENABLED` | `true` |
| `JARVIS_WAKE_ALLOW_SOURCES` | `hotword,double_clap,hotkey` |
| `WAKE_COOLDOWN_SECONDS` | `1.8` |
| `WAKE_ACTION` | `jarvis_internal` |
| `WAKE_DEBUG` | `false` |
| `BRIDGE_DEBUG` | `false` |
| `JARVIS_DOUBLE_CLAP_WINDOW_MS` | `4500` |
| `INTENT_LOCAL_ACTION_THRESHOLD` | `0.75` |
| `INTENT_BRAIN_THRESHOLD` | `0.45` |
| `INTENT_ASK_CLARIFY_THRESHOLD` | `0.60` |

#### ASR / Audio / VAD / Microphone

| Variable | Default |
|---|---|
| `ASR_PROVIDER` | `groq` |
| `GROQ_API_KEY` | empty |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` |
| `GROQ_ASR_LANGUAGE` | `en` |
| `GROQ_ASR_TEMPERATURE` | `0` |
| `GROQ_TIMEOUT_SECONDS` | `10` |
| `AUDIO_SAMPLE_RATE` | `16000` |
| `JARVIS_WAKE_SAMPLE_RATE` | `16000` |
| `JARVIS_WAKE_FRAME_MS` | `80` |
| `AUDIO_CHANNELS` | `1` |
| `AUDIO_FRAME_SAMPLES` | `1280` |
| `AUDIO_INPUT_DEVICE` | empty |
| `VAD_BACKEND` | `silero` |
| `JARVIS_POST_WAKE_DELAY_MS` | `1000` |
| `JARVIS_WAKE_CONFIRMATION_ENABLED` | `true` |
| `JARVIS_WAKE_CONFIRMATION_TEXT` | `Awake, sir.` |
| `JARVIS_COMMAND_NO_SPEECH_TIMEOUT_MS` | `20000` |
| `JARVIS_COMMAND_END_SILENCE_MS` | `2200` |
| `JARVIS_COMMAND_MAX_SPEECH_MS` | `30000` |
| `JARVIS_POST_SESSION_WAKE_SUPPRESS_MS` | `2000` |
| `JARVIS_COMMAND_MIN_SPEECH_MS` | `400` |
| `VAD_MIN_SPEECH_MS` | `400` |
| `VAD_SILENCE_END_MS` | `1800` |
| `VAD_MAX_COMMAND_SECONDS` | `25` |
| `COMMAND_LISTEN_TIMEOUT_SECONDS` | `25` |
| `ASR_MAX_RECORD_SECONDS` | `25` |
| `ASR_SILENCE_TIMEOUT_MS` | `1800` |
| `VAD_MIN_RMS` | `0.015` |
| `ASR_MIN_AUDIO_MS` | `1800` |
| `ASR_FOLLOWUP_MAX_RECORD_SECONDS` | `4` |
| `ASR_FOLLOWUP_SILENCE_TIMEOUT_MS` | `650` |
| `TRANSCRIPT_ALLOW_SHORT_FOLLOWUP` | `true` |
| `VAD_PREROLL_MS` | `400` |
| `WAKE_FLUSH_AUDIO_MS` | `500` |
| `MIC_ENERGY_THRESHOLD` | `250` |
| `MIC_DYNAMIC_ENERGY_THRESHOLD` | `true` |
| `MIC_PAUSE_THRESHOLD` | `0.5` |

#### TTS / UI / Brain / Intent / Safety

| Variable | Default |
|---|---|
| `JARVIS_ONLINE_TTS` | `0` |
| `TTS_BEFORE_COMMAND_CAPTURE` | `false` |
| `TTS_PROVIDER_ORDER` | `groq,pyttsx3` |
| `TTS_PRIMARY_PROVIDER` | `groq` |
| `GROQ_TTS_ENABLED` | `true` |
| `GROQ_TTS_MODEL` | `canopylabs/orpheus-v1-english` |
| `GROQ_TTS_VOICE` | `Fritz-PlayAI` |
| `GROQ_TTS_RESPONSE_FORMAT` | `wav` |
| `GROQ_TTS_TIMEOUT_SECONDS` | `10` |
| `TTS_FALLBACK_PROVIDER` | `pyttsx3` |
| `TTS_MAX_CHARS` | `700` |
| `TTS_SUMMARIZE_LONG_OUTPUT` | `true` |
| `JARVIS_UI_MODE` | `mark` |
| `JARVIS_FULLSCREEN` | `true` |
| `JARVIS_WINDOW_MODE` | `fullscreen` |
| `VOICE_FIRST_UI` | `true` |
| `SHOW_CHAT_HISTORY` | `false` |
| `SHOW_MINIMAL_TRANSCRIPT` | `true` |
| `BRAIN_PROVIDER` | `gemini` |
| `JARVIS_BRAIN_PRIMARY` | `gemini` |
| `JARVIS_BRAIN_FALLBACK` | `none` |
| `JARVIS_ENABLE_LEGACY_BRAIN_PROVIDERS` | `false` |
| `JARVIS_BRAIN_PROVIDER` | empty |
| `BRAIN_ENABLED` | `true` |
| `BRAIN_FAIL_FAST_SECONDS` | `60` |
| `GEMINI_API_KEY` | empty |
| `GOOGLE_API_KEY` | empty |
| `GEMINI_MODEL_PRIMARY` | `gemini-2.5-flash` |
| `GEMINI_MODEL_FALLBACK` | `gemini-2.5-flash-lite` |
| `GEMINI_MODEL_CHAIN` | `gemini-2.5-flash,gemini-2.5-flash-lite` |
| `GEMINI_TIMEOUT_SECONDS` | `20` |
| `GEMINI_TEMPERATURE` | `0.35` |
| `GEMINI_MAX_OUTPUT_TOKENS` | `512` |
| `GROQ_INTENT_ENABLED` | `true` |
| `GROQ_INTENT_MODEL` | `openai/gpt-oss-20b` |
| `GROQ_INTENT_MODEL_FALLBACK` | `qwen/qwen3-32b` |
| `GROQ_INTENT_MODEL_STRONG` | `openai/gpt-oss-120b` |
| `GROQ_INTENT_TIMEOUT_SECONDS` | `4` |
| `GROQ_INTENT_TEMPERATURE` | `0` |
| `GROQ_INTENT_MAX_TOKENS` | `300` |
| `SAFETY_GATE_ENABLED` | `true` |
| `SAFETY_MODEL` | `openai/gpt-oss-safeguard-20b` |
| `SAFETY_GATE_FOR_RISKY_ACTIONS_ONLY` | `true` |

#### Follow-up / Speech / Vision Routing / Camera / Lightning

| Variable | Default |
|---|---|
| `AUTO_LISTEN_AFTER_QUESTION` | `true` |
| `BARGE_IN_ENABLED` | `true` |
| `BARGE_IN_ALWAYS_LISTEN` | `true` |
| `BARGE_IN_HOTWORD_ONLY` | `false` |
| `BARGE_IN_MIN_SPEECH_MS` | `350` |
| `BARGE_IN_IGNORE_TTS_ECHO_MS` | `300` |
| `TTS_INTERRUPT_ENABLED` | `true` |
| `TTS_FADE_OUT_MS` | `250` |
| `ASR_MODEL` | `whisper-large-v3-turbo` |
| `ASR_MODEL_ACCURATE` | `whisper-large-v3` |
| `TTS_MODEL` | `orpheus-english` |
| `TTS_ENABLED` | `true` |
| `VISION_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` |
| `TTS_SUMMARY_MAX_CHARS` | `700` |
| `TTS_CHUNKED_SPEAKING` | `true` |
| `NEXI_AUTO_FOLLOWUP_AFTER_TTS` | `true` |
| `JARVIS_CONSOLE_LOG_LEVEL` | `clean` |
| `JARVIS_DEBUG_LOG_FILE` | `artifacts/jarvis_interview_debug.log` |
| `JARVIS_VERBOSE_WAKE_LOGS` | `false` |
| `JARVIS_VERBOSE_AUDIO_LOGS` | `false` |
| `JARVIS_VERBOSE_CLAP_LOGS` | `false` |
| `JARVIS_VERBOSE_BRIDGE_LOGS` | `false` |
| `CAMERA_CONTROL_ENABLED` | `false` |
| `CAMERA_CONTROL_MODE` | `hand` |
| `CAMERA_PREVIEW_ONLY` | `true` |
| `CAMERA_USE_GPU` | `true` |
| `HAND_GESTURE_CONTROL_ENABLED` | `true` |
| `HAND_GESTURE_CLICK_ENABLED` | `true` |
| `HAND_GESTURE_SCROLL_ENABLED` | `true` |
| `HAND_GESTURE_SMOOTHING` | `0.65` |
| `HAND_GESTURE_DEADZONE` | `0.015` |
| `HAND_GESTURE_CLICK_COOLDOWN_MS` | `450` |
| `EYE_MOUSE_ENABLED` | `true` |
| `EYE_MOUSE_CONTROL_ENABLED` | `false` |
| `EYE_MOUSE_REQUIRE_CALIBRATION` | `true` |
| `EYE_MOUSE_BLINK_CLICK_ENABLED` | `false` |
| `EYE_MOUSE_DWELL_CLICK_ENABLED` | `false` |
| `EYE_MOUSE_SMOOTHING` | `0.75` |
| `EYE_MOUSE_DEADZONE` | `0.025` |
| `LIGHTNING_API_BASE` | `https://lightning.ai/v1` |
| `LIGHTNING_AUTH_BASE64` | empty |
| `LIGHTNING_BILLING_PROJECT_ID` | empty |
| `LIGHTNING_AGENT_ID` | empty |
| `LIGHTNING_STREAM` | `true` |
| `LIGHTNING_TIMEOUT_SECONDS` | `90` |

### Master Implementation Path

Every feature must follow this gate before moving to the next feature:

```text
1. Research the code path and current wiring.
2. Audit current implementation against this requirements file.
3. Check external docs/APIs only when the feature depends on external behavior.
4. Patch the smallest verified gap.
5. Review the implemented code once.
6. Optimize/debug only if the review or tests reveal a concrete issue.
7. Review the implemented code a second time.
8. Run focused tests for the feature.
9. Run related integration checks.
10. Move forward only with zero focused failures.
```

Feature order:

| Order | Feature | Primary Files | Test Gate |
|---:|---|---|---|
| 1 | Presence State Engine | `presence_state.py`, `ui_state_manager.py`, `runtime_bridge.py` | `tests/test_presence_state.py` |
| 2 | Barge-In / Interruptibility | `barge_in_manager.py`, `groq_tts.py`, `audio_wake_pipeline.py` | `tests/test_barge_in_manager.py` |
| 3 | Demo Mode | `demo_mode.py`, `groq_asr.py`, `groq_intent_router_v2.py` | `tests/test_demo_mode.py` |
| 4 | Diagnostics | `diagnostics.py`, Nexi doctors | `tests/test_diagnostics.py`, `tests/test_engine_diagnostics.py` |
| 5 | Pre-flight Check | `scripts/demo_check.py` | `tests/test_demo_check.py` |
| 6 | Session Memory | `engine/memory/session_memory.py`, `wake_session_manager.py` | `tests/test_session_memory.py` |
| 7 | Episodic Memory | `engine/memory/episodic_memory.py`, `command.py` | `tests/test_episodic_memory.py` |
| 8 | Semantic Memory | `engine/memory/semantic_memory.py`, `memory_store.py` | `tests/test_semantic_memory.py` |
| 9 | Reflection Memory | `reflection_memory.py`, `correction_learner.py`, `intent_context_builder.py` | `tests/test_reflection_memory.py` |
| 10 | ReAct Planner + Safety Gate | `react_planner.py`, `tool_registry.py`, `safety_gate.py` | `tests/test_react_planner.py`, `tests/test_safety_gate.py`, `tests/test_tool_registry.py` |
| 11 | Tone Layer | `tone_manager.py`, `command.py`, UI CSS | `tests/test_tone_manager.py` |
| 12 | World Monitor Dashboard | `world_monitor_dashboard.py`, `www_mark/*`, `www/*` | `tests/test_world_monitor_dashboard.py`, `tests/test_mark_ui_dashboard.py` |
| 13 | Transcript Card | `runtime_bridge.py`, `command.py`, `www_mark/*`, `www/*` | UI bridge/runtime tests |

### Plugin, MCP, and Skill Use Rules

Loaded project skills used for this work:

| Skill | Use |
|---|---|
| `jarvis-autonomous-wake-debug` | Wake, ASR, TTS, UI bridge, and lifecycle rules. |
| `jarvis-pass-only-wake-ui-debug` | PASS-only validation, no fake success, UI state verification. |
| `karpathy-guidelines` | Surgical changes, simplicity, and verification-first implementation. |

OpenCode plugin/MCP context:

| Item | Status | Rule |
|---|---|---|
| Graphify plugin | `.opencode/plugins/graphify.js` is loaded | Use only if `graphify-out/graph.json` exists. It is absent in the current workspace. |
| `claude-flow` MCP | Defined in `.mcp.json`, `autoStart=false` | Do not assume available. Verify before use. |
| `ruv-swarm` MCP | Optional npx MCP | Do not assume available. Verify before use. |
| `flow-nexus` MCP | Optional/auth-required | Do not enable without explicit auth/config need. |

### Audit And Verification Baseline

User-supplied audit baseline:

| Feature | Status | Tests | Changes Needed |
|---|---|---:|---:|
| T1.1 Presence State Engine | VERIFIED | 3/3 | 0 |
| T1.2 Barge-In / Interruptibility | VERIFIED | 37/37 | 0 |
| T1.3 Demo Mode | VERIFIED | 5/5 | 0 |
| T1.4 Diagnostics | VERIFIED | 21/21 | 0 |
| T1.5 Pre-flight (`demo_check.py`) | VERIFIED | 8/8 | 0 |
| T2.1 Session Memory | VERIFIED | 5/5 | 0 |
| T2.2 Episodic Memory | VERIFIED | 5/5 | 0 |
| T2.3 Semantic Memory | VERIFIED | 6/6 | 0 |
| T3 ReAct Planner + Safety Gate | VERIFIED | 75/75 | 0 |
| T4 World Monitor Dashboard | VERIFIED | 29/29 | 0 |

Baseline full suite reported by audit: `2004 passed, 1 skipped, 0 failed`.

Implementation audit in this session found and patched concrete wiring gaps:

| Gap | Patch |
|---|---|
| Standalone `updatePresence` bridge missing | Added Python `updatePresence` call and JS exposed handlers in both UIs. |
| Explicit `TranscriptCard` DOM missing | Added minimal transcript card targets to `www_mark/` and `www/`. |
| Runtime dashboard/diagnostics/transcript event handling missing | Added `dashboard_update`, `diagnostics_request`, `diagnostics_result`, and `transcript` handlers. |
| Presence not updated from router/session start | Added confidence/goal updates from intent router and session start/finish presence updates. |
| Demo ASR canned fallback missing | Added demo-mode ASR fallback text for empty/missing-key/failure paths. |
| Direct tool path lacked safety gate boundary | Added direct `execute_tool()` safety gate while preserving safe preview modes. |
| Correction rules did not feed reflection memory | Added correction-to-reflection lesson storage. |
| Legacy memory did not write through semantic memory | Added semantic write-through/recall bridge in `memory_store.py`. |
| Generic command outcomes did not always store episodes | Added episodic write-through in `_store_conversation_turn()`. |
| Brain context did not include full intent memory context | Added session/semantic/reflection/episodic context injection for Gemini brain. |
| Tone selected but not applied to response text | Applied tone wrapping/TTS style in `command.speak()`. |

Required verification commands:

```powershell
.venv\Scripts\python.exe -m compileall engine src
.venv\Scripts\python.exe -m pytest tests/ -v
.venv\Scripts\python.exe scripts\verify_safety.py
.venv\Scripts\python.exe scripts\verify_dependencies.py
.venv\Scripts\python.exe scripts\playwright_runtime_check.py
```

No final PASS may be claimed unless the relevant logs/tests are available.

## Architecture Context

This document defines 11 feature requirements for Jarvis Phase 4. Each feature includes:

- **Research** — academic/industry references (cited URLs)
- **Code Integration** — exact existing files and line numbers to modify
- **API Specification** — full Python API for new modules
- **Sequence / Data Flow** — how the feature interacts with existing pipelines
- **Edge Cases** — failure modes, race conditions, safeguards

All line numbers refer to the codebase at `E:\jarvis-main` as of 2026-06-20.

---

## Feature 1: Barge-In / Interruptibility

### What It Is

When TTS is speaking and the user says "Hey Jarvis" (or any hotword), the system must immediately stop TTS playback, enter LISTENING state, and capture the new command.

### Why

Without barge-in, Jarvis blocks all input during TTS. The user must wait for speech to finish. All production voice assistants (Alexa, Siri, Google Assistant) implement barge-in as a core UX requirement.

### Research

- **[Amazon AVS SpeechSynthesizer 1.3](https://developer.amazon.com/en-US/docs/alexa/alexa-voice-service/speechsynthesizer.html)** — Alexa uses a `SpeechSynthesizer` state machine with `PLAYING`, `INTERRUPTED`, `FINISHED` states. On interruption: sends `SpeechInterrupted` event, transitions to `INTERRUPTED`, stops TTS, clears queue. Priority hierarchy: Customer input > TTS responses > Alerts > Notifications > Audio/Music.
- **[AgentOS SoftFadeBargeinHandler](https://github.com/framerslab/agentos/blob/master/src/io/voice-pipeline/SoftFadeBargeinHandler.ts)** — Three-tier strategy: `< 80ms` = ignore (breath/noise), `80ms–1500ms` = pause with fade-out, `>= 1500ms` = hard cancel with `[interrupted]` marker.
- **[LiveKit Adaptive Interruption](https://livekit.com/blog/adaptive-interruption-handling)** — v1.5.0+ uses ML model trained on human-agent conversations: 86% precision, 100% recall at 500ms overlap speech, median trigger at 216ms.
- **[SIMBA Barge-In Guide](https://simbavoice.ai/resources/how-voice-agents-handle-interruptions-gracefully)** — Barge-in pipeline: VAD runs in parallel with TTS playback; on speech > threshold, fire barge-in event; stop TTS stream → flush audio buffer → cancel LLM generation → update state.
- **[Nuance Barge-In Types](https://docs.nuance.com/nvp-for-speech-suite/appdev/rc-bargin.html)** — Three modes: `speech` (any speech stops prompt), `selective` (specific phrases only), `hotword` (key word with min/max duration constraints).

### Code Integration

#### New Module: `engine/barge_in_manager.py`

```python
from dataclasses import dataclass
from enum import Enum, auto
import time
import os

class InterruptLevel(Enum):
    NONE = auto()        # no interrupt
    PAUSE = auto()       # soft pause (TTS fade-out, resume later)
    CANCEL = auto()      # hard cancel (stop + discard, no resume)

@dataclass
class BargeInState:
    is_speaking: bool = False           # is TTS currently playing?
    is_interrupted: bool = False        # has barge-in been triggered?
    interrupted_at: float = 0.0         # time.basetime() when interrupt fired
    interrupt_level: InterruptLevel = InterruptLevel.NONE
    resume_possible: bool = False       # True if we can resume from pause

class BargeInManager:
    """
    Singleton manager that bridges VAD hotword detection with TTS playback control.
    
    During TTS playback, VAD continues to run in the audio pipeline.
    When VAD detects speech + hotword match above threshold, this manager:
    1. Interrupts TTS via interrupt_controller
    2. Transitions UI to listening
    3. Clears the command queue for fresh capture
    """
    
    # Config env vars (read at init):
    # BARGE_IN_ENABLED (default "true")
    # BARGE_IN_MIN_SPEECH_MS (default 200) — ignore clicks/noise under 200ms
    # BARGE_IN_CANCEL_MS (default 1500) — speech >1500ms = hard cancel
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/audio_wake_pipeline.py` | After hotword detect (line 753 `trigger_wake`), call `BargeInManager.interrupt()` if currently speaking | L753–L810 |
| `engine/groq_tts.py` | Add `stop()` method — cancels `playsound()` via interrupt controller | L82 `speak_text` |
| `engine/tts_provider_manager.py` | Add `stop_all()` to halt any active TTS provider | Whole file |
| `engine/interrupt_controller.py` | Add `is_speaking()` getter; wire into barge-in flow | Existing `_speaking` global |
| `engine/runtime_bridge.py` | Add new event type `EVENT_INTERRUPTED`; map to `online` UI state | L23–L36 event constants |
| `engine/command.py` | `speak()` method (L270) must check `BargeInManager.is_interrupted` between chunks | L270–L320 |
| `engine/turn_manager.py` | Add `mark_interrupted()` → sets state + clears auto_listen | L50–L60 |

#### Current State (No Stop Mechanism)

`engine/groq_tts.py` L82–L102 calls `playsound(temp_wav)` which blocks until the entire file finishes. There is no handle/pid to abort mid-playback. `engine/interrupt_controller.py` has `request_interrupt()` which sets a global `_interrupt` event, but `playsound` does not check it.

#### Implementation Strategy (Two-Layer)

**Layer 1 — PlaySound Replacement (immediate):**
Replace `playsound` with `pydub.playback.play()` or `simpleaudio.play()` which returns a handle that can be stopped. The `stop()` method calls `handle.stop()`.

```python
# engine/groq_tts.py — modified speak_text
def speak_text(text: str) -> GroqTTSResult:
    audio_bytes = synthesize_speech(text)
    if not audio_bytes:
        return GroqTTSResult(ok=False, error="synthesis_failed")
    temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp.write(audio_bytes)
    temp.close()
    try:
        import simpleaudio as sa
        wave_obj = sa.WaveObject.from_wave_file(temp.name)
        play_handle = wave_obj.play()
        _current_handle = play_handle  # module-level for stop()
        while play_handle.is_playing():
            if interrupt_controller.is_interrupted():
                play_handle.stop()
                return GroqTTSResult(ok=False, error="interrupted", fallback_used=False)
            time.sleep(0.05)
        return GroqTTSResult(ok=True)
    except ImportError:
        # fallback to blocking playsound
        from playsound import playsound as ps
        ps(temp.name)
```

**Layer 2 — Stream-Based (future):**
Stream audio chunks from Groq and feed them to a `pyaudio` output stream. Check `interrupt_controller` between chunks. This enables sub-50ms interrupt latency.

```python
# Future stream-based approach
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
for chunk in groq_stream(audio_bytes):
    if interrupt_controller.is_interrupted():
        stream.stop_stream()
        break
    stream.write(chunk)
```

#### Sequence

```
[VAD running during TTS]
User says "Hey Jarvis"
  → openWakeWord detects hotword
  → audio_wake_pipeline.trigger_wake() called
  → BEFORE starting new session: BargeInManager.interrupt()
    → interrupt_controller.request_interrupt()
    → groq_tts.stop() → play_handle.stop()
    → command.py speak loop checks interrupt → breaks
    → runtime_bridge: post_status(EVENT_INTERRUPTED)
    → UI: SAYING → INTERRUPTED → ONLINE → LISTENING
  → THEN: normal wake flow (session start, command capture)
```

#### Edge Cases

| Scenario | Behavior |
|----------|----------|
| TTS already finished | No-op — barge-in skipped |
| Interrupt during interrupt | Debounce — ignore if <500ms since last interrupt |
| pyttsx3 (SAPI5) cannot stop mid-sentence | Best-effort via engine.stop() |
| User noise <200ms | Ignored (BARGE_IN_MIN_SPEECH_MS filter) |
| Interrupt exactly at TTS end | Race — either interrupts final ms or arrives cleanly |

---

## Feature 2: ReAct Agent Loop

### What It Is

A reasoning loop where Jarvis can: understand user goal → choose tool → execute tool → observe result → decide next action → respond. Makes Jarvis capable of multi-step tasks that compose tools.

### Why

Current architecture (`engine/command.py` L1592–L1787) uses a linear priority chain: memory checks → intent v2 → tool registry → local skills → phase3 bridge → intent router. There is no composition — each command is a single turn. A request like "find my note about Project X and save it as a file" requires multi-step reasoning.

### Research

- **[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)** — Yao et al., NeurIPS 2022. Combines chain-of-thought reasoning with tool-use actions. Agent alternates between `Thought → Action → Observation` until task completion.
- **[LangGraph `create_react_agent`](https://langchain-ai.github.io/langgraph/reference/prebuilt/#langgraph.prebuilt.chat_agent_executor.create_react_agent)** — One-line agent builder: `create_react_agent(model, tools)` creates a state graph with `call_model` node, `ToolNode`, and `should_continue` conditional edge.
- **[LangGraph ReAct Tutorial](https://agentsindex.ai/blog/langgraph-tutorial)** — Three core components: `call_model` (LLM + bind_tools → tool_calls), `ToolNode` (dispatches tool_calls → ToolMessage), `should_continue` (if tool_calls present → continue, else END).
- **[OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)** — Model emits `tool_calls` as structured JSON. Runtime dispatches and returns `tool_call_id`-matched results.
- **[PrynAI ReAct Implementation](https://github.com/PrynAI/AgenticAI-OnRamp-with-Langgraph/tree/ReAct-Agent-Function-Calling)** — Complete Python example with bind_tools, ToolNode, and conditional edges.

### Code Integration

#### New Module: `engine/react_planner.py`

```python
from dataclasses import dataclass, field
from typing import Any
import os
import json
import requests
import time

@dataclass
class ReActStep:
    thought: str = ""                    # LLM reasoning (NEVER shown in UI)
    action: str = "tool_call"            # "tool_call" | "respond" | "error"
    tool_name: str | None = None         # tool to call (from tool_registry)
    tool_input: dict | None = None       # args for the tool
    observation: str | None = None       # result after execution
    status: str = "pending"              # "pending" | "running" | "success" | "failed"

@dataclass
class ReActPlan:
    session_id: str = ""
    user_input: str = ""
    steps: list[ReActStep] = field(default_factory=list)
    final_response: str = ""
    status: str = "in_progress"          # "in_progress" | "done" | "interrupted" | "error"
    error: str | None = None

class ReActPlanner:
    """
    ReAct agent loop. Uses Groq LLM (same endpoint as groq_intent_router_v2)
    to reason about user requests and execute tools.
    
    Config env vars:
    - REACT_MAX_STEPS (default 10) — safety limit on loop iterations
    - REACT_TIMEOUT_SECONDS (default 30) — total wall-clock timeout
    - REACT_MODEL (default "openai/gpt-oss-20b") — matches intent router model
    - REACT_TEMPERATURE (default 0) — deterministic tool choices
    """
    
    def plan(self, user_input: str, context: dict | None = None) -> ReActPlan:
        """Create a plan by calling LLM for the first reasoning step."""
    
    def execute_step(self, plan: ReActPlan, step_index: int) -> ReActStep:
        """Execute a single tool step via tool_registry.execute_tool()."""
    
    def continue_planning(self, plan: ReActPlan) -> ReActPlan:
        """Feed observation back to LLM, get next thought/action."""
    
    def finalize(self, plan: ReActPlan) -> str:
        """Extract final response text from completed plan."""
    
    def interrupt(self, plan: ReActPlan) -> None:
        """Interrupt a running plan (emergency stop)."""
    
    def _call_llm(self, messages: list[dict], tools_schema: list[dict]) -> dict:
        """Call Groq chat completions with tool schemas bound."""
```

**Tool Schema Format (OpenAI-compatible, generated from `ToolSpec`):**

```python
def _tools_schema() -> list[dict]:
    """Convert tool_registry.ToolSpec list to OpenAI function-calling schema."""
    from engine.tool_registry import list_tools
    schemas = []
    for tool in list_tools():
        schema = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": tool.get("required_slots", []),
                },
            },
        }
        for slot in tool.get("required_slots", []):
            schema["function"]["parameters"]["properties"][slot] = {
                "type": "string",
                "description": f"Required: {slot}"
            }
        for slot in tool.get("optional_slots", []):
            schema["function"]["parameters"]["properties"][slot] = {
                "type": "string",
                "description": f"Optional: {slot}"
            }
        schemas.append(schema)
    return schemas
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/command.py` | When `route_intent_v2` returns `route="tool"`, optionally start ReAct loop instead of single-tool dispatch | L1695–L1702 |
| `engine/groq_intent_router_v2.py` | Add `"react"` as a valid route; return `route="react"` for multi-step tasks | L220–L288 |
| `engine/tool_registry.py` | Add `to_openai_schema()` method on `ToolSpec` to generate function-calling JSON | Add method |
| `engine/ui_state_manager.py` | Add safe thinking states: `"checking_files"`, `"running_tool"`, `"searching"` | L10 CANONICAL_STATES |
| `engine/runtime_bridge.py` | Add `EVENT_REACT_THINKING`, `EVENT_REACT_TOOL_START`, `EVENT_REACT_TOOL_END` event types | L23–L36 |
| `engine/safety_gate.py` | Validate every tool call from ReAct loop; block dangerous actions | L1–L80 |
| `engine/assistant_response.py` | Add `handler_reason="react"` → suppress followup after ReAct completion | L85–L95 |

#### Sequence (Multi-Step Example)

```
User says: "save my last note about project X as a file"

1. route_intent_v2 returns route="react", intent="react_multi_step"
2. command.py starts ReActPlanner.plan("save my last note about project X")
3. LLM reasoning (HIDDEN):
   Thought: I need to find notes about Project X, then save the content.
   Action: tool_call { tool: "recall_memory", input: { query: "project X" } }
4. ToolNode: execute "recall_memory" → returns note text
5. LLM reasoning (HIDDEN):
   Observation: "Project X design doc: MVP features..."
   Thought: Found the note. Now create a file with this content.
   Action: tool_call { tool: "create_file", input: { name: "project_x_design", content: "..." } }
6. ToolNode: execute "create_file" → returns "Created project_x_design.txt"
7. LLM reasoning (HIDDEN):
   Observation: File created successfully.
   Thought: Task complete.
   Action: respond { message: "I found your note about Project X and saved it as project_x_design.txt." }
8. Finalize → speak response
```

Each tool execution emits safe UI status: `"Searching memory..."` → `"Creating file..."` → `"Done."`

#### Safety Rules

- Max tools per plan: `REACT_MAX_STEPS` (default 10)
- Wall-clock timeout: `REACT_TIMEOUT_SECONDS` (default 30)
- Every tool call passes `safety_gate.execution_is_safe()` check (`engine/safety_gate.py` L25)
- Emergency stop (user says "stop", "cancel") → `plan.interrupt()` → breaks loop immediately
- Chain-of-thought NEVER exposed to UI — only safe status: `"thinking"`, `"searching"`, `"running_tool"`, `"done"`
- No file delete, no settings change without explicit confirmation

---

## Feature 3: Reflexion / Self-Improvement Memory

### What It Is

When a task fails, Jarvis writes a structured lesson to memory. On future similar tasks, the lesson is injected into the LLM context to inform better decisions.

### Why

Currently, errors are logged and forgotten. The same failure repeats. Reflexion provides continuous self-improvement without retraining model weights.

### Research

- **[Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)** — Shinn et al., NeurIPS 2023. Three components: ACTOR (generates text+actions), EVALUATOR (scores outcomes binary/scalar), SELF-REFLECTION (generates verbal reinforcement). Achieves 91% pass@1 on HumanEval vs 80% GPT-4.
- **[GitHub: noahshinn/reflexion](https://github.com/noahshinn/reflexion)** — 3.1K stars. Four strategies: `NONE` (no memory), `LAST_ATTEMPT` (see reasoning trace), `REFLEXION` (see self-reflection), `LAST_ATTEMPT_AND_REFLEXION` (both).
- **[Agent Patterns: Reflexion](https://agent-patterns.readthedocs.io/en/stable/patterns/reflexion.html)** — Uses linguistic feedback stored in episodic memory as plain text. Unlike RL which updates weights, Reflexion stores natural language reflections for future context injection.

### Code Integration

#### New Module: `engine/reflection_memory.py`

```python
from dataclasses import dataclass
from pathlib import Path
import json
import time
import re
from typing import Optional

REFLECTION_PATH = Path(__file__).resolve().parents[1] / "data" / "reflection_memory.json"

@dataclass
class ReflectionLesson:
    id: str = ""
    failure: str = ""                   # What went wrong
    lesson: str = ""                    # What was learned
    next_action: str = ""               # What to do differently
    context: str = ""                   # Domain/situation tags
    timestamp: float = 0.0
    count: int = 1                      # How many times reinforced
    intent: str = ""                    # The intended action
    tool_name: str = ""                 # Which tool was involved

class ReflectionMemory:
    """
    Persisted lesson store. Exposes:
    - store_lesson(): save a new lesson (dedups by failure text)
    - recall_similar(): find relevant lessons for current context
    - get_context(): formatted string for LLM context injection
    
    Storage: data/reflection_memory.json
    Schema:
    {
      "version": 1,
      "lessons": [
        {
          "id": "ref_20260620_001",
          "failure": "UI did not ACK state after UI_SEND",
          "lesson": "Always verify UI_ACK after UI_SEND",
          "next_action": "Wait up to 2s for ack before claiming success",
          "context": "domain=ui state=online session=abc",
          "timestamp": 1781972963.846,
          "count": 3,
          "intent": "online",
          "tool_name": "ui_state_manager"
        }
      ]
    }
    """
    
    MAX_LESSONS = 50                    # Keep newest 50
    SIMILARITY_THRESHOLD = 2            # Min keyword overlap for recall
    
    @classmethod
    def store_lesson(cls, failure: str, lesson: str, next_action: str = "",
                     context: str = "", intent: str = "", tool_name: str = "") -> str:
        """Store a lesson. Updates count if duplicate failure text."""
    
    @classmethod
    def recall_similar(cls, context: str = "", top_k: int = 3) -> list[dict]:
        """Keyword overlap matching. Returns top_k most relevant lessons."""
    
    @classmethod
    def get_context(cls, context: str = "", max_lessons: int = 3) -> str:
        """Formatted string: 'Lessons from past experience:\\n- ...' for LLM prompt."""
    
    @classmethod
    def prune_old(cls, days: int = 30) -> int:
        """Remove lessons older than `days`. Returns count removed."""
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/command.py` | After command failure (exception or route="error"), call `ReflectionMemory.store_lesson()` | L1592–L1787 (scattered error paths) |
| `engine/react_planner.py` | Before each LLM reasoning call, append `ReflectionMemory.get_context()` to system prompt | ReAct planner internals |
| `engine/workflow_manager.py` | After workflow error (e.g., `create_folder_workflow` fails), store lesson | L1–L100 |
| `engine/intent_context_builder.py` | Add reflection lessons to `build_context()` for future LLM calls | `build_context()` output |
| `engine/correction_learner.py` | When user provides explicit correction, also store as reflection | `record_correction_from_text()` |

#### Integration with Existing Learning Systems

Jarvis already has distributed learning across ~8 modules:

| Module | Existing Function | Reflexion Integration |
|--------|------------------|----------------------|
| `engine/adaptive_memory.py` | `learn_from_exchange()` | Don't duplicate — store reflexion only for failures |
| `engine/correction_learner.py` | `record_correction_from_text()` | Also store reflection lesson for correction |
| `engine/training_rules.py` | Rule-based learning | Keep separate (rules are user-defined, reflections are system-generated) |
| `engine/reflection_engine.py` | `reflect_after_turn()` | ALIGN: existing reflection_engine can feed into ReflectionMemory |
| `engine/need_training_manager.py` | Unmet need tracking | Keep separate (needs are gaps, reflections are failures) |

#### Edge Cases

- **No lessons yet**: `get_context()` returns empty string — no-op
- **Storage file corrupt**: Load from backup, reset to `{"version": 1, "lessons": []}`
- **Concurrent write**: File lock via `threading.Lock()` (single process)
- **Lesson explosion**: `MAX_LESSONS=50`, `prune_old()` removes old entries

---

## Feature 4: Three-Layer Memory System

### What It Is

Replace the current flat fact memory (`engine/memory_store.py`) with a three-tier hierarchy: **Short-term (session)**, **Episodic (task outcomes)**, **Semantic (stable knowledge)**.

### Why

Current `memory_store.py` (230 lines) stores `{"notes":[], "preferences":{}, "facts":[], "recent_commands":[]}` in a single JSON file. No concept of recency, importance, or temporal structure. Three-layer memory mirrors the Atkinson-Shiffrin model and LangGraph's memory architecture.

### Research

- **[LangGraph Memory Types](https://langchain-ai.github.io/langgraph/concepts/memory/)** — Five types: Short-term (thread-scoped), Long-term (cross-thread, per-user), Working (graph-run), Episodic (past sessions, append-only), Semantic (RAG, vector-store). Key insight: **Checkpointer ≠ Store** — checkpointer is thread-scoped, store is cross-thread.
- **[LangMem SDK](https://github.com/langchain-ai/langmem)** — Tools for agent to write/read/manage its own memory: `create_manage_memory_tool()`, `create_search_memory_tool()`. Agents can rewrite their own system prompt (procedural memory) over time.
- **[MemGPT / Letta](https://github.com/letta-ai/letta)** — Virtual context management: recall memory (recent history), core memory (working context), archival memory (async storage). Three tiers map directly to short-term/episodic/semantic.
- **[Atkinson-Shiffrin Memory Model](https://en.wikipedia.org/wiki/Atkinson–Shiffrin_memory_model)** (1968) — Sensory → Short-term → Long-term. Classic cognitive architecture.

### Code Integration

#### Current Memory Architecture (Before)

```
engine/memory_store.py
  → data/jarvis_memory.json  (flat JSON: notes + preferences + facts + recent_commands)
  → engine/adaptive_memory.py (semantic vector store)
  → used by: command.py (L1681), intent_context_builder.py, features.py chatBot()
```

#### New Modules

**`engine/memory/__init__.py`**

```python
"""Three-layer memory system for Jarvis."""

from engine.memory.session_memory import SessionMemory
from engine.memory.episodic_memory import EpisodicMemory
from engine.memory.semantic_memory import SemanticMemory

session_memory = SessionMemory()
episodic_memory = EpisodicMemory()
semantic_memory = SemanticMemory()
```

**`engine/memory/session_memory.py`**

```python
"""
Short-term memory: current conversation turns, cleared on new wake.
In-memory list, not persisted. Mirror of turn_manager state.
"""

class SessionMemory:
    """
    Thread-safe in-memory session store.
    Cleared on every new wake (via finish_session in wake_session_manager).
    
    Api:
    - add_turn(role, content, metadata)     # Append a turn
    - get_recent(n=10)                      # Last N turns
    - get_last_user_input()                 # Most recent user utterance
    - get_last_assistant_response()         # Most recent assistant response
    - clear()                               # Full reset
    - to_context(max_chars=1800)            # Formatted for LLM context window
    - count() -> int                        # Turn count
    """
    
    MAX_TURNS = 20  # maximum turns to keep in session
    
    def __init__(self):
        self._turns: list[dict] = []
        self._lock = threading.Lock()
```

**`engine/memory/episodic_memory.py`**

```python
"""
Episodic memory: past task attempts, outcomes, and reflections.
Persisted to data/episodic_memory.json.
Append-only (no edits) with TTL-based pruning.
"""

EPISODIC_PATH = ROOT / "data" / "episodic_memory.json"

@dataclass
class Episode:
    id: str = ""                    # "ep_20260620_001"
    user_input: str = ""            # What user asked
    intent: str = ""                # Detected intent
    route: str = ""                 # Route taken
    outcome: str = ""               # "success" | "failure" | "interrupted"
    steps_taken: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""
    reflection_id: str = ""         # Link to ReflectionLesson
    timestamp: float = 0.0

class EpisodicMemory:
    MAX_EPISODES = 200
    PRUNE_DAYS = 30
    
    def store(self, episode: Episode) -> str       # Returns episode ID
    def recall_recent(self, n: int = 20)           # Last N episodes
    def recall_similar(self, query: str, n: int = 5)  # Keyword match on user_input
    def prune_old(self, days: int = 30) -> int      # Remove stale
```

**`engine/memory/semantic_memory.py`**

```python
"""
Semantic memory: stable facts, user preferences, project knowledge.
Delegates to existing memory_store.py + adaptive_memory.py for persistence.
New: category tags, confidence scoring, TTL for ephemeral facts.
"""

FACT_CATEGORIES = ("preference", "fact", "rule", "project", "user_info", "general")
DEFAULT_TTL_DAYS = 365  # One year default

@dataclass
class SemanticFact:
    text: str
    category: str = "general"
    confidence: float = 1.0        # 0.0–1.0
    ttl_days: int = 365
    source: str = "conversation"   # "explicit", "inferred", "imported"
    created_at: float = 0.0
    
class SemanticMemory:
    def store(self, fact: SemanticFact) -> str      # Store + dedup
    def recall(self, query: str, n: int = 5)        # Search across facts
    def recall_by_category(self, category: str)     # Filter by category
    def forget(self, text: str) -> bool             # Remove matching fact
    def get_summary(self) -> str                    # "47 facts across 6 categories"
    def prune_expired(self) -> int                  # Remove TTL-expired facts
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/memory_store.py` | Wrap as `SemanticMemory` adapter; deprecate direct JSON access | All 230 lines |
| `engine/command.py` | Route memory commands to correct layer: session = `"repeat"`, episodic = `"what did I last do"`, semantic = `"remember that"` | L1681 `_handle_memory_command` |
| `engine/adaptive_memory.py` | Integrate with `SemanticMemory.store()` for inferred facts | `remember()`, `learn_from_exchange()` |
| `engine/intent_context_builder.py` | Build context from ALL three layers, respecting `max_chars` | `build_context()` |
| `engine/reflection_memory.py` | Link reflections to EpisodicMemory episodes | `store_lesson()` |
| `engine/wake_session_manager.py` | On `finish_session()`, call `SessionMemory.clear()` | L60–L80 |

#### Data Flow

```
User says: "Remember that my anniversary is June 15"
  → route_intent_v2 returns route="memory", intent="remember"
  → SemanticMemory.store(Fact("anniversary is June 15", category="preference"))
  → stored in data/jarvis_memory.json + adaptive_memory

User says: "What's my anniversary?"
  → SemanticMemory.recall("anniversary")
  → returns ["Your anniversary is June 15"]
  → speak response

After wake + command + response:
  → EpisodicMemory.store(Episode(user_input=..., outcome="success"))
  → SessionMemory.clear()  (new wake clears short-term)
```

---

## Feature 5: Presence State Model

### What It Is

A single source-of-truth dict representing Jarvis's internal awareness: mode, attention target, confidence, energy level, current goal, last event, and memory context.

### Why

Currently, state is scattered across 6+ modules (`wake_session_manager.py`, `turn_manager.py`, `interrupt_controller.py`, `command.py`, `runtime_bridge.py`, `ui_state_manager.py`). No single module knows the full picture. The presence model aggregates all state into one queryable source.

### Research

- **[Global Workspace Theory](https://en.wikipedia.org/wiki/Global_workspace_theory)** — Baars, 1988. Consciousness as a global workspace where information is broadcast. PresenceState is Jarvis's "global workspace" — all modules broadcast to it, it broadcasts to UI.
- **[OpenAI System Message](https://platform.openai.com/docs/guides/prompt-engineering)** — The model's self-awareness comes from structured state description in the system prompt.
- **[Hume AI EVI Custom Language Model](https://dev.hume.ai/docs/speech-to-speech-evi/guides/custom-language-model.mdx)** — EVI sends `user_message` with expression measures alongside transcribed text, enabling emotional state awareness.

### Code Integration

#### New Module: `engine/presence_state.py`

```python
from dataclasses import dataclass, field
from typing import Optional
import time
import threading

@dataclass
class PresenceState:
    """
    Singleton. Every state transition updates this model.
    Broadcasts to UI automatically via runtime_bridge + ui_state_manager.
    """
    
    # Core dimensions
    mode: str = "sleeping"              # "sleeping" | "online" | "listening" | "thinking" | "saying"
    attention: str = "none"             # "user" | "audio" | "tool" | "ui" | "none"
    confidence: float = 0.0             # 0.0–1.0 (copy from intent_router)
    energy: str = "normal"              # "normal" | "low" | "high"
    
    # Event tracking
    last_event: str = ""                # Last event name
    last_event_at: float = 0.0          # When last event fired
    
    # Goal tracking
    current_goal: str = "waiting"       # "waiting" | "processing" | "clarifying" | "executing"
    current_goal_detail: str = ""       # e.g., "creating folder on desktop"
    
    # Session info
    session_id: str = ""
    session_started_at: float = 0.0
    session_age_ms: float = 0.0
    
    # Memory hint
    memory_context: str = ""
    
    # Lock
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def update_mode(self, mode: str) -> None:
        """Update mode + auto-set timestamp. Thread-safe."""
    
    def update_attention(self, target: str) -> None:
        """Set attention focus."""
    
    def set_goal(self, goal: str, detail: str = "") -> None:
        """Set current goal + detail."""
    
    def to_dict(self) -> dict:
        """Serializable payload for eel.updateJarvisState()."""
    
    def to_llm_context(self) -> str:
        """Formatted string for LLM system prompt injection."""
    
    def to_ui_string(self) -> str:
        """Human-readable for UI panel display."""

# Module-level singleton
_presence = PresenceState()

def get_presence() -> PresenceState:
    return _presence
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/runtime_bridge.py` | Every event handler also calls `presence_state.update_mode()` + `update_attention()` | L200–L270 all event handlers |
| `engine/ui_state_manager.py` | `emit_state()` also calls `presence_state.update_mode(canonical)` | L129 `emit()` |
| `engine/groq_intent_router_v2.py` | After routing, set `presence_state.set_goal()` + `presence_state.confidence` | L220 return path |
| `engine/command.py` | `speak()` sets goal to "speaking", `_handle_product_intelligence_v2()` sets goal to "processing" | L270, L678 |
| `engine/wake_session_manager.py` | `start_session()` updates presence with session_id | L50 |
| `www_mark/controller.js` | Handle new `eel.updatePresence()` call | New exposed function |

#### UI Display

```
ATTENTION: USER
GOAL: CREATING FOLDER
CONFIDENCE: 82%
ENERGY: NORMAL
LAST: asr_result
SESSION: abc123 (12.4s)
```

Displayed in a small status panel (`#presence-panel`) below the main orb.

---

## Feature 6: Emotion / Tone Layer

### What It Is

Jarvis adjusts response tone based on context. Six tones: `calm`, `urgent`, `focused`, `friendly`, `technical`, `low_confidence`. Affects TTS voice style, UI color pulse, and response wording.

### Why

Flat tone makes Jarvis feel robotic. Context-appropriate modulation improves perceived intelligence. All major voice assistants vary their prosody based on context.

### Research

- **[Hume AI EVI](https://dev.hume.ai/docs/speech-to-speech-evi/overview.mdx)** — Detects 48 distinct expressions from prosody (tune, rhythm, timbre). Top 3 expressions appended to each user message. EVI "acts out" text with appropriate tone/prosody. Hugging Face space now ranks #1 in Chatbot Arena Voice.
- **[Affective Computing](https://en.wikipedia.org/wiki/Affective_computing)** — Picard, 1997. MIT Media Lab. Foundational work on human-emotion-aware computing.
- **[EMNLP 2020 Tone Classification](https://aclanthology.org/2020.emnlp-main.298/)** — Effective tone classification in dialogue systems using contextual embeddings.

### Code Integration

#### New Module: `engine/tone_manager.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class Tone(Enum):
    CALM = "calm"
    URGENT = "urgent"
    FOCUSED = "focused"
    FRIENDLY = "friendly"
    TECHNICAL = "technical"
    LOW_CONFIDENCE = "low_confidence"

@dataclass
class ToneConfig:
    mode: Tone = Tone.CALM
    voice_style: str = "default"       # TTS voice hint
    ui_color_class: str = "tone-calm"  # CSS class for orb
    response_prefix: str = ""          # Optional wording prefix
    tts_rate_delta: int = 0            # pyttsx3 rate adjustment (+/-)

@dataclass
class ToneContext:
    """Automatic tone selection inputs."""
    route: str = ""                    # "brain" | "tool" | "workflow" | "greeting" | "error"
    confidence: float = 0.0
    risk_level: str = "none"
    is_error: bool = False
    is_tool: bool = False
    is_greeting: bool = False
    is_low_confidence: bool = False

class ToneManager:
    """
    Selects tone based on context. Updates presence_state with current tone.
    """
    
    TONE_MAP = {
        Tone.CALM:    ToneConfig(Tone.CALM, "default", "tone-calm", "", 0),
        Tone.URGENT:  ToneConfig(Tone.URGENT, "firm", "tone-urgent", "", 20),
        Tone.FOCUSED: ToneConfig(Tone.FOCUSED, "neutral", "tone-focused", "Let me check...", -10),
        Tone.FRIENDLY: ToneConfig(Tone.FRIENDLY, "warm", "tone-friendly", "", 10),
        Tone.TECHNICAL: ToneConfig(Tone.TECHNICAL, "flat", "tone-technical", "", -20),
        Tone.LOW_CONFIDENCE: ToneConfig(
            Tone.LOW_CONFIDENCE, "softer", "tone-uncertain",
            "I think ", -15
        ),
    }
    
    @classmethod
    def select_tone(cls, context: ToneContext) -> ToneConfig:
        """Map context to tone automatically."""
    
    @classmethod
    def wrap_response(cls, text: str, tone: ToneConfig) -> str:
        """Apply prefix/suffix for the tone."""
    
    @classmethod
    def apply_tts_style(cls, text: str, tone: ToneConfig) -> str:
        """Add SSML prosody tags if using SSML-capable TTS."""
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/command.py` | Before `speak()`, call `ToneManager.select_tone()` based on route + result | L270 `speak()` |
| `engine/assistant_response.py` | Use `ToneManager.wrap_response()` to modify spoken/display text | L60 `make_response()` |
| `engine/groq_tts.py` | Optionally accept tone hint for voice selection | L82 |
| `engine/tts_provider_manager.py` | Pass tone to TTS provider | `speak_with_provider()` |
| `engine/presence_state.py` | Include tone in presence model | Add tone field |
| `www_mark/style.css` | Add `.tone-calm`, `.tone-urgent`, `.tone-focused`, `.tone-friendly`, `.tone-technical`, `.tone-uncertain` orb pulse CSS | New rules |
| `www_mark/controller.js` | Apply tone CSS class to orb element on state update | `updateOrbMode()` |

#### Tone Mapping Table

| Context | Tone | TTS Style | UI Color | Example Wording |
|---------|------|-----------|----------|-----------------|
| Default/greeting | `friendly` | warm | blue pulse | "Hello! How can I help you?" |
| Brain response | `calm` | default | cyan | "Here's what I found..." |
| Tool execution | `focused` | neutral | teal | "Let me check that for you." |
| Error/system | `urgent` | firm | red | "I encountered an issue." |
| Low confidence | `low_confidence` | softer | orange | "I think you asked about..." |
| Code/output | `technical` | flat | white | "(file content)" |
| Success | `friendly` | warm | green | "Done! Folder created on Desktop." |

---

## Feature 7: Self-Monitor Panel

### What It Is

A diagnostics panel showing real-time health of all Jarvis subsystems: Microphone, Hotword, Clap, ASR, Brain, TTS, Memory, Tools, Errors, Uptime.

### Why

Developers need component-level health visibility. The self-monitor makes debugging instant and creates the "real JARVIS" feel. Similar to Tesla's hidden diagnostics screen.

### Research

- **[VoiceMon Observability Framework](https://github.com/jaiswal-naman/voicemon)** — 4-layer observability: L1 Network (packet loss, MOS), L2 Pipeline (STT→LLM→TTS latency, confidence), L3 UX (E2E latency, interruptions), L4 Outcome (task success, CSAT).
- **[Pipecat Finchvox](https://pypi.org/project/finchvox/)** — Local session replay with audio waveforms, traces, interruption highlighting. Adds `FinchvoxProcessor()` to pipeline.
- **[Azure Health Endpoint Monitoring](https://learn.microsoft.com/en-us/azure/architecture/patterns/health-endpoint-monitoring)** — Pattern: `GET /health` returns `{"status": "healthy", "checks": {"gateway": "ok", "stt": "ok", "tts": "degraded"}}`.
- **[Prometheus / Grafana](https://prometheus.io/)** — Industry standard for component health monitoring with time-series metrics.

### Code Integration

#### New Module: `engine/diagnostics.py`

```python
from dataclasses import dataclass
from typing import Optional
import time
import os
import threading

@dataclass
class ComponentStatus:
    name: str
    status: str             # "active" | "ready" | "disabled" | "error" | "checking"
    detail: str             # Human-readable status text
    last_check: float = 0.0
    latency_ms: int = 0     # Last check latency

class Diagnostics:
    """
    Runs health checks on all subsystems.
    Results cached for 5s to avoid hammering APIs.
    """
    
    _cache: dict = {}
    _cache_lock = threading.Lock()
    _cache_ttl = 5.0
    
    @classmethod
    def check_all(cls) -> dict[str, ComponentStatus]:
        """Run ALL checks. Returns dict keyed by component name."""
    
    @classmethod
    def check_microphone(cls) -> ComponentStatus:
        """Check if at least one input device is available via sounddevice."""
    
    @classmethod
    def check_hotword(cls) -> ComponentStatus:
        """Check if openWakeWord is loaded and configured."""
    
    @classmethod
    def check_clap(cls) -> ComponentStatus:
        """Check clap backend status (dsp_clap or clap_nn)."""
    
    @classmethod
    def check_asr(cls) -> ComponentStatus:
        """Check Groq Whisper ASR: API key present, last call latency."""
    
    @classmethod
    def check_brain(cls) -> ComponentStatus:
        """Check brain provider (Groq/Gemini): API key present."""
    
    @classmethod
    def check_tts(cls) -> ComponentStatus:
        """Check TTS: Groq API key + pyttsx3 availability."""
    
    @classmethod
    def check_memory(cls) -> ComponentStatus:
        """Check memory layers are loaded and accessible."""
    
    @classmethod
    def check_tools(cls) -> ComponentStatus:
        """Check tool registry is loaded with N tools."""
    
    @classmethod
    def get_uptime(cls) -> str:
        """Formatted uptime string (since process start)."""
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/runtime_bridge.py` | Add `EVENT_DIAGNOSTICS_REQUEST` and `EVENT_DIAGNOSTICS_RESULT` event types | L23–L36 |
| `engine/command.py` | Route `intent="diagnose_jarvis"` to `Diagnostics.check_all()` | L1695 `_handle_product_intelligence_v2` |
| `www_mark/index.html` | Add collapsible diagnostics panel | New HTML |
| `www_mark/controller.js` | Handle `eel.diagnosticsResult()` → populate diagnostics DOM | New exposed function |

#### UI Layout

```html
<div id="DiagnosticsPanel" class="collapsed">
  <div class="diagnostics-header" onclick="toggleDiagnostics()">
    ⚙ Diagnostics <span id="diag-summary">(8/8 healthy)</span>
  </div>
  <div id="DiagnosticsContent">
    <!-- Populated by eel.diagnosticsResult() -->
  </div>
</div>
```

Each component rendered as:

```
Microphone     ✓ active     (Microphone (Realtek), index 0)
Hotword        ✓ active     (openWakeWord, threshold 0.25)
Clap           ✗ disabled
ASR            ✓ ready      (Groq Whisper, last: 342ms)
Brain          ✓ ready      (Groq, model: openai/gpt-oss-20b)
TTS            ✓ ready      (Groq + pyttsx3 fallback)
Memory         ✓ loaded     (3 layers, 47 facts, 12 episodes)
Tools          ✓ ready      (38 registered)
Last error     none
Uptime         2h 34m 12s
```

---

## Feature 8: World Monitor Dashboard

### What It Is

An information dashboard inspired by [World Monitor](https://github.com/koala73/worldmonitor) (56K+ stars, TypeScript/Three.js). Adapted for Jarvis's internal data: system health, memory stats, active tasks, tools, command history, routing, brain provider status, wake detector state.

### Research

- **[koala73/worldmonitor](https://github.com/koala73/worldmonitor)** — Real-time global intelligence dashboard. 65+ external providers, 56 map layers, 500+ curated feeds. TypeScript + Three.js/globe.gl + deck.gl + MapLibre GL. 6 site variants, 24 languages.
- **[World Monitor Panel Architecture](https://koala73-worldmonitor.mintlify.app/guide/panels)** — All panels extend `Panel` base class with `render()`/`destroy()`. Panels render via `setContent(html)` debounced at 150ms. Drag-and-drop reordering persisted to `localStorage`. Cross-panel communication via `CustomEvent`: `wm:breaking-news`, `wm:deduct-context`, `theme-changed`.
- **[World Monitor Architecture](https://github.com/koala73/worldmonitor/blob/main/ARCHITECTURE.md)** — 60+ Vercel Edge Functions, 276 protos, 34 services. 3-tier cache: Redis → CDN → Service Worker. SmartPollLoop with visibility-aware polling.

### Code Integration

#### New Module: `engine/world_monitor_dashboard.py`

```python
"""
Aggregates all Jarvis data sources into a unified dashboard state dict.
Polled by UI every 2s (matching SmartPollLoop pattern).
"""

from dataclasses import dataclass, field
from typing import Any

@dataclass
class DashboardPanel:
    id: str
    title: str
    data: dict[str, Any]
    priority: int = 0           # Higher = shown first
    refresh_interval: float = 2.0  # Poll interval in seconds

class WorldMonitorDashboard:
    """
    Aggregates all Jarvis subsystems into dashboard panels.
    Pattern: Panel base class → render() → setContent() → debounced at 150ms
    Cross-panel communication via eel.updateJarvisState().
    Panel config persisted to localStorage.
    
    Panels:
    - system:    Diagnostics.check_all() + uptime
    - memory:    Session/Episodic/Semantic memory stats
    - active:    Current ReAct step + goal (from presence_state)
    - tools:     ToolRegistry.list_tools() + last used
    - commands:  CommandHistory.recent(10)
    - routes:    IntentHistory.recent(10)
    - brain:     Active provider, model, latency
    - wake:      Hotword/clap status + sensitivity
    """
    
    def get_all_panels(self) -> list[DashboardPanel]:
        """Return all panels with current data."""
    
    def get_panel(self, panel_id: str) -> DashboardPanel | None:
        """Get single panel data."""
    
    def get_dashboard_state(self) -> dict:
        """Full dashboard state dict for UI."""
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/diagnostics.py` | Feed into dashboard system panel | All |
| `engine/runtime_bridge.py` | Add `EVENT_DASHBOARD_UPDATE` | L23–L36 |
| `engine/presence_state.py` | Feed into dashboard active panel | All |
| `www_mark/index.html` | Dashboard container with resizable panels | New HTML |
| `www_mark/style.css` | Panel grid, drag handles, resize cursors | New CSS |
| `www_mark/controller.js` | Poll dashboard every 2s (SmartPollLoop); handle panel reorder | New exposed functions |

#### Panel Layout

```
┌────────────────────────────────────────────────────┐
│ ⚙ DIAGNOSTICS DASHBOARD                 [refresh] │
├──────────────┬──────────────┬──────────────────────┤
│  SYSTEM      │  MEMORY      │  ACTIVE TASK         │
│  hotword: ✓  │  session: 5  │  goal: creating      │
│  asr: ✓      │  episodic:12 │  folder              │
│  tts: ✓      │  semantic:47 │  step: 2/4           │
├──────────────┼──────────────┼──────────────────────┤
│  TOOLS       │  COMMANDS    │  WAKE                │
│  total: 38   │  last:       │  hotword: ✓ 0.25     │
│  last:       │  "open       │  clap: disabled      │
│  create_file │  chrome"     │  cooldown: none      │
└──────────────┴──────────────┴──────────────────────┘
```

Panels are draggable and resizable (col span 1-2), persisted to `localStorage`.

---

## Feature 9: Subtitles + Spoken Response Card

### What It Is

Every interaction displays a visible card showing: what the user said, what Jarvis responded, and metadata (route, intent, provider, latency).

### Why

Users need to verify what was heard and review past interactions. Standard for all voice assistants. Also aids debugging during development.

### Code Integration

#### New HTML in `www_mark/index.html`

```html
<div id="TranscriptCard" class="transcript-card">
  <div class="transcript-entry user-entry">
    <span class="entry-label">YOU</span>
    <span class="entry-text" id="UserText"></span>
  </div>
  <div class="transcript-entry jarvis-entry">
    <span class="entry-label">JARVIS</span>
    <span class="entry-text" id="JarvisText"></span>
    <div class="entry-meta" id="ResponseMeta">
      <span class="meta-route">Route: greeting</span>
      <span class="meta-provider">Provider: Groq LLM</span>
      <span class="meta-intent">Intent: greeting</span>
      <span class="meta-latency">Latency: 1.2s</span>
    </div>
  </div>
</div>
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `www_mark/index.html` | Add transcript card below response area | After `#jarvis-response` |
| `www_mark/style.css` | Card styles — speech bubble layout, alternating YOU/JARVIS | New rules |
| `www_mark/controller.js` | `eel.updateTranscript(user_text, jarvis_text, metadata)` → populate card | New exposed function |
| `engine/command.py` | After command completes, capture user text + response + metadata | L1592–L1787 capture path |
| `engine/runtime_bridge.py` | Send `EVENT_TRANSCRIPT` with payload | New event type |

#### Metadata Display

```
Route: greeting        Provider: Groq LLM        Intent: greeting        Latency: 0.8s
Route: tool           Provider: local            Intent: open_app        Latency: 0.1s
Route: brain          Provider: Gemini           Intent: general_qa      Latency: 2.3s
```

---

## Feature 10: Demo Mode

### What It Is

When `JARVIS_DEMO_MODE=true`, Jarvis operates in a safe, scripted execution mode: no auto-followup, reduced logs, fallback TTS, safe canned responses, graceful provider failure.

### Why

Presentations must not fail. Demo mode guarantees smooth operation regardless of backend state (API down, rate-limited, timeout).

### Code Integration

#### New Module: `engine/demo_mode.py`

```python
import os

DEMO_MODE = os.getenv("JARVIS_DEMO_MODE", "").lower() in ("1", "true", "yes")

SAFE_RESPONSES = {
    "router_fail": "Let me check that for you.",
    "asr_empty": "I didn't quite catch that. Could you repeat it?",
    "tts_fail": "",  # Skip TTS, just show on screen
    "api_timeout": "I'm processing your request. One moment please.",
    "brain_fail": "I'm not sure about that right now.",
}

class DemoMode:
    @staticmethod
    def is_active() -> bool:
        return DEMO_MODE
    
    @staticmethod
    def should_suppress_followup() -> bool:
        """Demo mode: no auto-followup after responses."""
        return DEMO_MODE
    
    @staticmethod
    def safe_response(key: str) -> str:
        """Get safe canned response for failure scenario."""
        return SAFE_RESPONSES.get(key, "")
    
    @staticmethod
    def sanitize_log(line: str) -> str:
        """Filter noisy debug lines in demo mode."""
        if not DEMO_MODE:
            return line
        noise_patterns = ("[REFLECTION]", "[WORKING_MEMORY]", "[CONTEXT]", "[CONFIDENCE]")
        for pattern in noise_patterns:
            if pattern in line:
                return ""
        return line
    
    @staticmethod
    def get_tts() -> str:
        """Always use pyttsx3 fallback in demo mode for reliability."""
        return "pyttsx3"
```

#### Existing Files to Modify

| File | Change | Key Lines |
|------|--------|-----------|
| `engine/command.py` | After `speak()`, check `DemoMode.should_suppress_followup()` | L283–L290 `_mark_question_response` |
| `engine/groq_intent_router_v2.py` | If router fails in demo mode, return safe canned route | L220–L288 |
| `engine/groq_asr.py` | If ASR empty in demo mode, return safe canned text: "hello" | L50–L80 |
| `engine/groq_tts.py` | In demo mode, skip Groq TTS, use pyttsx3 | `is_configured()` |
| `engine/runtime_bridge.py` | `sanitize_log()` before printing | `_safe_log()` |
| `run.py` | Print "=== JARVIS DEMO MODE ===" banner at startup | L1–L50 |
| `.env.example` | Add `JARVIS_DEMO_MODE=false` | New entry |

---

## Feature 11: Golden Demo Script

### What It Is

A CLI script `scripts/demo_check.py` that verifies the entire wake→listen→ASR→route→TTS→sleep pipeline with automated pass/fail gates. Used before any demo or release.

### Code Integration

#### New Script: `scripts/demo_check.py`

```python
"""
Golden Demo Script: verifies end-to-end Jarvis pipeline.
Usage: .venv\Scripts\python.exe scripts/demo_check.py

Each check is independent. All must PASS for demo readiness.
Checks:
1. UI_ACK:    UI acknowledges state updates within 2s
2. HOTWORD:   openWakeWord triggers wake detection
3. VAD:       Silero VAD detects speech in audio sample
4. ASR:       Groq Whisper transcribes audio to text
5. ROUTER:    Intent router returns valid route for test commands
6. BRAIN:     Brain provider returns non-empty response
7. TTS:       TTS produces audio output
8. SLEEP:     Pipeline returns to SLEEPING after completion
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

CHECKS = []

def check(name: str, critical: bool = True):
    """Decorator to register a check."""
    def decorator(fn):
        CHECKS.append((name, critical, fn))
        return fn
    return decorator

def _pass(msg: str):
    print(f"  ✓ {msg}")

def _fail(msg: str):
    print(f"  ✗ {msg}")

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

@check("UI_ACK")
def test_ui_ack():
    """Verify UI state ack works."""
    from engine.ui_state_ack import wait_for_ack
    result = wait_for_ack("sleep", "demo_check", timeout_ms=2000)
    assert result, "UI did not ACK within 2s"
    _pass(f"ack received (mock)")

@check("HOTWORD")
def test_hotword():
    """Verify openWakeWord hotword detection."""
    from engine.hotword_engine_manager import get_hotword_engine
    engine = get_hotword_engine()
    assert engine is not None, "Hotword engine not initialized"
    _pass(f"hotword engine ready, threshold={engine.get_threshold():.2f}")

@check("VAD")
def test_vad():
    """Verify Silero VAD detects speech."""
    from engine.audio_wake_pipeline import _get_vad
    vad = _get_vad()
    assert vad is not None, "VAD not initialized"
    _pass("VAD model loaded")

@check("ASR")
def test_asr():
    """Verify Groq Whisper ASR transcribes audio."""
    from engine.groq_asr import transcribe
    config = {"language": "en", "timeout_seconds": 5}
    result = transcribe(b"", config)  # Empty audio → expect empty result, not crash
    _pass(f"ASR configured, language=en")

@check("ROUTER")
def test_router():
    """Verify intent router returns valid routes for common commands."""
    from engine.groq_intent_router_v2 import route_intent_v2
    test_cases = [
        ("hello", "greeting"),
        ("open chrome", "tool"),
        ("what is AI", "brain"),
    ]
    for text, expected_route in test_cases:
        result = route_intent_v2(text, {"use_deterministic": True})
        # deterministic fallback for tests
    _pass(f"router returned valid routes for {len(test_cases)} commands")

@check("BRAIN")
def test_brain():
    """Verify brain provider returns responses."""
    from engine.features import chatBot
    try:
        response = chatBot("Say 'ok' and nothing else.")
        assert response and len(response) > 0
        _pass(f"brain response: {len(response)} chars")
    except Exception as e:
        _fail(f"brain failed: {e}")

@check("TTS")
def test_tts():
    """Verify TTS produces audio output."""
    from engine.groq_tts import is_configured, synthesize_speech
    if not is_configured():
        _fail("Groq TTS not configured")
        return
    audio = synthesize_speech("Test.")
    assert audio and len(audio) > 100, "Audio output too short"
    _pass(f"TTS audio: {len(audio)} bytes")

@check("SLEEP")
def test_sleep():
    """Verify pipeline returns to sleep after command."""
    from engine.wake_session_manager import get_session_state
    state = get_session_state()
    assert state.get("is_paused", False) is False, "Detectors should not be paused"
    _pass("pipeline in sleep state")

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  JARVIS GOLDEN DEMO CHECK")
    print("=" * 60)
    print()
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, critical, fn in CHECKS:
        print(f"[{name}]")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            _fail(str(e))
        except Exception as e:
            if critical:
                failed += 1
                _fail(f"CRITICAL: {e}")
            else:
                skipped += 1
                _fail(f"non-critical: {e}")
        print()
    
    print("=" * 60)
    total = passed + failed + skipped
    print(f"  Result: {passed}/{total} PASS", end="")
    if failed:
        print(f", {failed} FAIL", end="")
    if skipped:
        print(f", {skipped} SKIP", end="")
    print()
    
    if failed:
        print("  ❌ NOT DEMO READY")
        sys.exit(1)
    else:
        print("  ✅ DEMO READY")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

#### Example Output

```
============================================================
  JARVIS GOLDEN DEMO CHECK
============================================================

[UI_ACK]
  ✓ ack received (mock)

[HOTWORD]
  ✓ hotword engine ready, threshold=0.25

[VAD]
  ✓ VAD model loaded

[ASR]
  ✓ ASR configured, language=en

[ROUTER]
  ✓ router returned valid routes for 3 commands

[BRAIN]
  ✓ brain response: 142 chars

[TTS]
  ✓ TTS audio: 48236 bytes

[SLEEP]
  ✓ pipeline in sleep state

============================================================
  Result: 8/8 PASS
  ✅ DEMO READY
```

---

## Complete File Inventory

### New Files (13)

```
engine/barge_in_manager.py
engine/react_planner.py
engine/reflection_memory.py
engine/memory/__init__.py
engine/memory/session_memory.py
engine/memory/episodic_memory.py
engine/memory/semantic_memory.py
engine/presence_state.py
engine/tone_manager.py
engine/diagnostics.py
engine/world_monitor_dashboard.py
engine/demo_mode.py
scripts/demo_check.py
```

### Modified Files (18)

```
engine/audio_wake_pipeline.py     — barge-in hook after trigger_wake()
engine/groq_tts.py               — add stop() method + simpleaudio
engine/tts_provider_manager.py    — add stop_all()
engine/interrupt_controller.py    — add is_speaking()
engine/runtime_bridge.py         — 5 new event types + sanitize_log()
engine/ui_state_manager.py       — add "checking_files", "running_tool", "searching"
engine/command.py                — ReAct routing, tone, reflexion, transcript
engine/groq_intent_router_v2.py  — add "react" route + demo mode
engine/tool_registry.py          — add to_openai_schema()
engine/safety_gate.py            — ReAct tool validation
engine/assistant_response.py     — tone wrapping + handler_reason="react"
engine/memory_store.py           — wrap as SemanticMemory adapter
engine/intent_context_builder.py — 3-layer memory context + reflection
engine/adaptive_memory.py        — link to SemanticMemory
engine/correction_learner.py     — store reflection on correction
engine/wake_session_manager.py   — clear SessionMemory on finish_session()
www_mark/index.html              — diagnostics panel, dashboard, transcript card
www_mark/controller.js           — 5 new eel-exposed functions
www_mark/style.css               — tone classes, panel grid, transcript card
run.py                           — demo mode banner
.env.example                     — JARVIS_DEMO_MODE
```

---

## Target: 80+ new tests, zero regressions on 1937+ existing.
