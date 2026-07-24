# Nexi Structure Before Nexi Access

This records the repository after lifecycle stabilization but before Router V3, ResponseCoordinator, live intelligence, and Spotify PKCE are introduced.

## Runtime Shape

- `run.py`: Windows process orchestration for the UI assistant, wake listener, alarms, and supporting workers.
- `main.py`: Eel/Edge UI runtime and bridge pump setup.
- `engine/audio_wake_pipeline.py`: wake candidate arbitration, VAD capture, ASR dispatch, audio-side session authority, barge-in transactions, and TTS watchdog dispatch.
- `engine/runtime_bridge.py`: ordered cross-process events, accepted session generations, command execution tracking, UI-side TTS interruption, and terminal coordination.
- `engine/wake_session_manager.py`: audio-process voice session, detector lock, TTS leases, cooldown leases, progress deadlines, and watchdog requests.
- `engine/command.py::allCommands`: legacy top-level command flow and primary TTS entry point.
- `engine/groq_intent_router_v2.py`: current semantic feature router with deterministic matching and optional Groq classification.
- `engine/tool_registry.py`: strongest existing candidate for one capability source of truth.
- `engine/assistant_response.py` and `engine/tts_response_manager.py`: partial response shaping, follow-up inference, hallucination guard, spoken/display splitting, and TTS chunks.

## Current Strengths

- Deterministic emergency, cancel, approval, and local action paths precede broad model fallback.
- Tool registry distinguishes risk, confirmation, handlers, aliases, examples, and model visibility.
- Model-facing approval/cancellation authority is explicitly restricted.
- Action success can be guarded by `success=True` and `verified=True` receipts.
- The repaired voice lifecycle uses session IDs, session epochs, ordered lifecycle sequences, producer IDs, bounded leases, watchdog ACKs, cooldown completion, and UI acknowledgements.
- Browser and desktop write actions use approval gates.

## Current Fragmentation

- `engine/command.py::allCommands`, `Phase3CommandBridge`, local skills, Groq Router V2, the legacy intent router, and `dispatch_intent` all participate in routing.
- `assistant_response.py`, `tts_response_manager.py`, `command.speak`, the runtime bridge, and UI state manager all participate in response behavior.
- `engine/local_skills.web_search` opens a browser search instead of retrieving structured live evidence.
- Browser intelligence expects a debug browser or Playwright session and is not yet a full accessibility-first semantic browser layer.
- Spotify has only browser/search-level behavior; no Web API PKCE client, secure refresh token, device resolver, or verified playback receipt exists.
- No single Router V3 currently owns deterministic, semantic, clarification, and brain fallback decisions.
- No single ResponseCoordinator currently owns one-visible-result, speech/display selection, stale-result suppression, and response completion.

## Migration Constraint

Nexi Access must be introduced behind existing contracts. Router V3 should consume the current tool registry, and ResponseCoordinator should consume typed outcomes from existing dispatch rather than creating a second executor. The existing voice lifecycle must remain authoritative while routing and response authority are consolidated.
