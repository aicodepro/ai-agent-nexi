# Authority Map Before Nexi Access

## Voice Session Authority

Authoritative process: audio process.

- Owner: `engine/wake_session_manager.py`.
- Event producer/consumer: `engine/audio_wake_pipeline.py`.
- Cross-process contract: `engine/runtime_bridge.py` control and command queues.
- Generation identity: `(session_id, session_epoch)`.
- TTS identity: voice `producer_id` or global `lease_id`, plus monotonic lifecycle sequence.
- Recovery: bounded progress timeout and ACK-gated TTS watchdog.

The UI process may request transitions and report TTS lifecycle events, but it does not independently finish or replace the audio session generation.

## UI State Authority

- Backend emitter: `engine/ui_state_manager.py`.
- Frontend reducer: `www_mark/controller.js`.
- Correlation: exact session ID, session epoch, canonical state, and sequence.
- Acknowledgement store: `engine/ui_state_ack.py`.

The backend is the source of truth. The frontend may render and acknowledge accepted state but must not invent lifecycle progress.

## Routing Authority

Current authority is fragmented.

1. `engine.command.allCommands` handles command-bus reentry and early deterministic handlers.
2. `Phase3CommandBridge.try_handle()` handles newer subsystems.
3. `engine.intent_router.route_intent()` classifies broad local/greeting/identity/brain routes.
4. `engine.command.dispatch_intent()` handles legacy feature branches.
5. `engine.groq_intent_router_v2.route_intent_v2()` is called in additional semantic paths and is the most capable feature router.
6. `engine.features.chatBot()` is the final conversational provider fallback.

There is no single entry that can currently prove every utterance was considered against the same capability manifest and confidence policy.

## Capability Authority

Best available source: `engine/tool_registry.py`.

It owns names, descriptions, examples, slots, safety, confirmation, handler paths, aliases, categories, enablement, and model visibility. Static alias tables and legacy dispatch branches still duplicate part of this information.

## Execution Authority

- Tool dispatch and handler resolution: `engine/tool_registry.py` plus legacy command dispatch.
- Safety policy: `engine/control/safety.py` and approval gates.
- Human approval: `engine/approval_queue.py`.
- Browser write operations: `engine/browser_intelligence.py` after approval.
- Desktop write operations: `engine/computer_use.py` after approval.

Model output is not authority to authenticate, approve, execute, or verify an action.

## Response Authority

Current response ownership is split:

- `engine/assistant_response.py`: response envelope and unverified-success guard.
- `engine/tts_response_manager.py`: spoken shortening and chunking.
- `engine/command.py::speak`: display update, TTS provider invocation, follow-up inference, TTS lease lifecycle, and cooldown.
- `engine/runtime_bridge.py`: generation acceptance, stale event rejection, and command terminal behavior.
- `engine/ui_state_manager.py`: visible state updates.

Target: one ResponseCoordinator should select one accepted outcome per generation and then delegate display and speech to these lower-level components.
