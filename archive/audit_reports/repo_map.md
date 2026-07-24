# Repository Map — Nexi / Jarvis

## Runtime Entrypoints
- `run.py` — Main launcher: spawns UI process + audio process + schedule/alarm processes
- `main.py` — UI process entry: Eel server, Edge window, calls `start_nexi()`
- `engine/command.py` — `allCommands()` — legacy Eel-exposed command entrypoint
- `engine/command_bus.py` — `submit_user_command()` — unified command entrypoint (preferred)

## Voice Modules
- `engine/audio_wake_pipeline.py` — Main wake pipeline (mic → openWakeWord → VAD → ASR → command)
- `engine/wake_session_manager.py` — Session lifecycle (start/finish/stale detection)
- `engine/voice_state_machine.py` — Strict voice lifecycle state machine
- `engine/hotword_engine_manager.py` — OpenWakeWord model management
- `engine/clap_backend_manager.py` — Clap detection orchestration
- `engine/dsp_clap_backend.py` — DSP-based double clap detector
- `engine/clap_nn_backend.py` — Neural clap detector
- `engine/silero_vad.py` — Silero VAD for speech detection
- `engine/groq_asr.py` — Groq Whisper ASR
- `engine/groq_tts.py` — Groq TTS
- `engine/tts_provider_manager.py` — TTS provider chain
- `engine/tts_response_manager.py` — TTS response building/summarization
- `engine/barge_in_manager.py` — Barge-in during TTS
- `engine/interrupt_controller.py` — TTS interrupt controller
- `engine/post_tts_cleanup.py` — Cooldown/cleanup after TTS
- `engine/nexi_wake_controller.py` — Internal wake/sleep state

## Router Modules
- `engine/groq_intent_router_v2.py` — **Primary intent router** (v2): deterministic + LLM (Groq/Gemini)
- `engine/intent_router.py` — Legacy deterministic router (still used as fallback in `allCommands()`)
- `engine/intent_pre_router.py` — Pre-routing corrections before main router
- `engine/intent_taxonomy.py` — Route schema, allowed routes/intents/domains
- `engine/intent_validator.py` — Result validation against schema
- `engine/intent_context_builder.py` — Builds context for router (session/semantic/episodic/reflection)
- `engine/intent_explainer.py` — Records and explains last intent decision
- `engine/confidence_manager.py` — Scores confidence, decides clarify vs execute
- `engine/slot_normalizer.py` — Normalizes slot names
- `engine/llm_parameter_extractor.py` — LLM-based slot extraction
- `engine/correction_learner.py` — Applies learned corrections to routing
- `engine/transcript_filter.py` — Filters gibberish/non-English transcripts

## Tool / Feature Modules
- `engine/tool_registry.py` — Tool registration, execution, slot validation, clarification messages
- `engine/tool_manifest_loader.py` — Router-facing capability manifest generation
- `engine/tool_result_verifier.py` — Verifies tool results (path exists, explicit verified flag)
- `engine/tool_usage_intelligence.py` — Tracks tool success rates, alias resolution
- `engine/tool_category_view.py` — UI-facing tool categories
- `engine/local_skills.py` — Local skill handlers (open_app, open_website, web_search)
- `engine/computer_use.py` — Screen read, click, type tools
- `engine/browser_intelligence.py` — Browser read, tabs, console, click, fill
- `engine/os_awareness.py` — OS state tools (active window, running apps, system state)
- `engine/net_awareness.py` — Network tools (connectivity, IP, WiFi)
- `engine/storage_awareness.py` — Storage tools (disk, battery)
- `engine/windows_settings.py` — Windows Settings openers
- `engine/feature_requests.py` — Feature request logging
- `engine/skill_library.py` — Skill catalog/listing
- `engine/app_intelligence.py` — Best-app-for-task resolution

## Brain / Model Modules
- `engine/features.py` — `chatBot()`, `ask_brain()`, provider chain (Gemini, HugChat, Lightning)
- `engine/gemini_brain.py` — Gemini API integration
- `engine/lightning_gateway.py` — Lightning AI gateway
- `engine/providers/` — Provider registry (DeepSeek, GLM, Qwen, Kimi, MiniMax)
- `engine/prompt_loader.py` — Loads system prompts from files
- `engine/react_planner.py` — ReAct multi-step planner

## Memory Modules
- `engine/memory_store.py` — Simple fact/note memory
- `engine/autonomous_memory.py` — Short-term conversation memory
- `engine/adaptive_memory.py` — Learns from exchanges
- `engine/correction_learner.py` — Records corrections
- `engine/reflection_engine.py` — Post-turn reflection
- `engine/reflection_memory.py` — Stores learned lessons
- `engine/memory/` — Subsystem: semantic, episodic, session, preference memory
- `engine/conversation_context.py` — Rolling conversation buffer
- `engine/context_budget_manager.py` — Token-bounded context builder
- `engine/memory_candidate_extractor.py` — Extracts candidates for semantic memory
- `engine/session_summary_manager.py` — Session summarization

## Approval / Safety Modules
- `engine/approval_queue.py` — Human approval queue for risky actions
- `engine/safety_gate.py` — Safety check before tool execution
- `engine/tool_result_verifier.py` — Post-execution verification
- `engine/control/safety.py` — EmergencyStop, SandboxPolicy

## Agency / Autonomy Modules
- `engine/agency/__init__.py` — Nexi Agency Engine tool wrappers
- `engine/agency/workflow_engine.py` — Pass-based workflow engine (planner→research→tool→verify→reflect→report)
- `engine/agency/nexi_tool_proxy.py` — Tool proxy with safety gate
- `engine/workflow_state.py` — Single-active conversational workflow state
- `engine/workflow_manager.py` — Workflow management
- `engine/workflow_dialog_manager.py` — Workflow dialogue handler

## Dialogue / Follow-up Modules
- `engine/turn_manager.py` — Turn lifecycle, auto-listen request
- `engine/followup_manager.py` — Pending followup state
- `engine/smart_followup_engine.py` — Resolves followup answers
- `engine/clarification_manager.py` — Clarification state for missing slot
- `engine/assistant_response.py` — Question detection, response building
- `engine/create_folder_workflow.py` — Example conversational slot-filling workflow

## UI / HUD Modules
- `engine/ui_state_manager.py` — Canonical UI state emission
- `engine/ui_loader.py` — Eel UI loading, Edge window args
- `engine/ui_adapter.py` — UI adapter functions
- `engine/ui_event_bridge.py` — UI event bridge
- `engine/ui_state_ack.py` — UI state acknowledgment
- `engine/output_actions.py` — Output workspace management
- `engine/output_router.py` — Routes assistant output to workspace vs speech
- `engine/presence_state.py` — HUD presence state (mode, attention, goal)
- `engine/runtime_awareness.py` — HUD diagnostics

## UI Frontend
- `www/` — Legacy UI (HTML/CSS/JS)
- `www_mark/` — Mark UI (newer design)
- `www/index.html` — Legacy entry point
- `www/controller.js` — UI state controller
- `www/style.css` — Legacy styles
- `www_mark/index.html` — Mark UI entry point
- `www_mark/controller.js` — Mark UI controller

## Tests
- `tests/` — 329 test files covering all subsystems
- `tests/conftest.py` — Shared test fixtures
- `tests/test_routing_master_flow.py` — Master routing flow
- `tests/test_nexi_agency_workflows.py` — Agency workflow tests
- `tests/test_command_bus.py` — Command bus tests
- `tests/test_audio_wake_pipeline.py` — Wake pipeline tests

## Other Key Files
- `requirements.txt` — Python dependencies
- `.env.example` — Configuration template
- `agent/skills/` — Agent skill definitions
- `scripts/` — Utility scripts
- `config/` — Configuration files
- `data/nexi/agency/` — Workflow run persistence
- `models/` — ML models (ONNX, etc.)
- `tools/` — Tool code
