# Authority Map After Nexi Access Increment

## Session And Voice

- Audio-process authority remains `engine/wake_session_manager.py` and `engine/audio_wake_pipeline.py`.
- Cross-process generation identity is `(session_id, session_epoch)`.
- TTS producers are bound by producer ID or global lease ID, monotonic lifecycle sequence, heartbeat renewal, cooldown, and ACK-gated watchdog shutdown.
- Barge-in requests carry the originating session epoch; stale generations cannot interrupt current speech.

## Routing

- Live semantic entry: `engine.router_v3.route_intent_v3`.
- `engine.command._handle_product_intelligence_v2` retains its compatibility name but imports Router V3, not Groq Router V2.
- Router V3 fingerprints the dynamic tool manifest and records route latency/source in `RouterTrace`.
- Groq Router V2 is an internal compatibility tier during migration, not a caller-facing authority.
- Capability descriptions, slots, risk, confirmation, aliases, and handlers remain owned by `engine/tool_registry.py`.

## Response

- Acceptance/deduplication authority: `engine/response_coordinator.py`.
- `engine.command.speak` consults the coordinator for every command-bus request.
- One request ID in one session generation can produce one accepted response.
- Older generations and duplicate request responses are rejected before display/TTS.
- TTS playback remains delegated to existing provider and lifecycle modules; the coordinator does not create a second speech engine.

## Live Information

- Authority: `engine/live_intelligence.py`.
- Retrieval order: configured Brave/Tavily providers, then DuckDuckGo retrieval.
- A live result is verified only when at least one citation URL is returned.
- Temporal storage: `engine/memory/temporal_memory.py` with source, valid time, retrieval time, expiry, confidence, citations, and explicit stale-only behavior.
- Provider failure never silently falls back to model memory. Cached output is labelled unavailable/stale.

## Spotify

- OAuth authority: `SpotifyOAuth` in `engine/integrations/spotify.py`.
- Redirect URI: `http://127.0.0.1:43821/callback`.
- Token authority: Windows Credential Manager target `Nexi/SpotifyOAuth`.
- Playback authority: Spotify Web API plus currently-playing readback.
- `spotify_connect` is hidden from model-visible tools and requires explicit deterministic user wording.
- Playback is not reported successful until the player state matches the selected track/context or control outcome.

## Accessibility And Automation

- Status authority remains backend `engine/ui_state_manager.py`; every payload includes canonical label, session generation, sequence, and non-visual earcon name.
- Optional local earcon playback is owned by `engine/accessibility_feedback.py` and controlled by `NEXI_EARCONS_ENABLED`.
- Transcript acceptance authority is `engine.transcript_filter.assess_transcript` at the command bus.
- Desktop actions prefer UI Automation semantic controls; raw keyboard injection is fallback.
- Browser actions prefer Playwright role/text/label selectors.
- Unavailable screen/browser reads return explicit unverified partial failure, never verified success.

## Remaining Compatibility Debt

- Groq Router V2 still implements Router V3's production compatibility tier internally.
- Legacy early command handlers remain before Router V3 for deterministic emergency, workflow, memory, output, and safety behavior.
- Some direct non-command speech can bypass request-level deduplication because it intentionally has no command request ID.
