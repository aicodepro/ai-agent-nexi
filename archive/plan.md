# Jarvis Autonomous Memory + Voice State Machine Plan

> Root plan for implementing automatic last-10-exchange short-term memory, rolling session summary, safe long-term memory extraction, and a strict voice lifecycle that prevents Jarvis from listening for new full commands while recognizing, thinking, or speaking.

## Goal

Build two connected systems:

```txt
1. Autonomous short-term memory
   - remembers the latest 10 user-assistant exchanges automatically
   - keeps current plans, decisions, and recent details available
   - summarizes older turns instead of sending full chat history
   - saves only durable useful facts to long-term memory

2. Voice state machine
   - SLEEPING -> LISTENING -> RECORDING_UTTERANCE -> RECOGNIZING -> THINKING -> SPEAKING -> COOLDOWN
   - stops normal command listening during recognition, thinking, and TTS
   - allows only interrupt words during speaking
   - resumes cleanly after TTS cooldown
```

Important rule:

```txt
Store recent context automatically.
Store permanent memory selectively.
Never listen for a new full command while recognizing, thinking, or speaking.
```

---

## 1. Codebase Research Findings

### 1.1 Existing short-term memory pieces

Jarvis already has several memory layers, but they are not unified into the exact autonomous last-10-exchange design.

Current relevant files:

```txt
engine/memory/conversation_buffer.py
engine/conversation_context.py
engine/memory/session_memory.py
engine/memory_store.py
engine/adaptive_memory.py
engine/memory_safety.py
engine/intent_context_builder.py
engine/memory/episodic_memory.py
engine/memory/semantic_memory.py
```

Observed details:

- `engine/memory/conversation_buffer.py:8-30` has a `ConversationBuffer`, but `_max_turns = 5`, not 10.
- `ConversationBuffer.append_turn()` stores user + assistant together as one exchange and redacts/rejects sensitive text through `classify_memory_text()` and `redact_sensitive()`.
- `engine/conversation_context.py:11` has `_turns = deque(maxlen=30)`, but it stores individual role turns, not explicitly 10 user-assistant exchanges.
- `engine/conversation_context.py:62-83` can build recent working memory context, currently defaulting to 10 role turns.
- `engine/memory/session_memory.py:43-48` has `SessionMemory(max_turns=20)`, but `wake_session_manager.finish_session()` clears it when a wake session ends.
- `engine/wake_session_manager.py:61-64` clears session memory at session start.
- `engine/wake_session_manager.py:119-122` clears session memory again at session finish.
- `engine/command_bus.py:45-58` already stores user input in `engine.conversation_context`, `engine.memory.session_memory`, and `engine.adaptive_memory.learn_from_user_text()`.
- `engine/memory_store.py:102-105` builds long-term memory context through adaptive memory.
- `engine/adaptive_memory.py:170-185` extracts memories only on explicit trigger-like phrases such as `remember that`, `from now on`, `i prefer`, `actually`, etc.
- `engine/memory_safety.py:6-39` already blocks/redacts API keys, tokens, passwords, secrets, cookies, private keys, bearer tokens, credit-card-like numbers, and similar sensitive content.
- `engine/intent_context_builder.py:91-105` currently includes only 4 recent turns by default for router context.
- `engine/intent_context_builder.py:157-168` combines session, episodic, semantic, and reflection memory into intent context.

Conclusion:

```txt
The repo already has memory primitives, but it needs a canonical autonomous exchange memory manager:
- exact latest 10 user-assistant exchanges
- rolling summary for older exchanges
- bounded context builder
- selective long-term extraction
- no clearing of cross-turn short-term context after each wake session
```

### 1.2 Existing long-term memory and safety pieces

Current long-term-ish storage:

```txt
engine/adaptive_memory.py              -> adaptive categorized memories
engine/memory_store.py                 -> legacy facts/notes wrapper
engine/memory/semantic_memory.py       -> semantic facts
engine/memory/episodic_memory.py       -> task episodes
engine/reflection_memory.py            -> lessons/failures
```

Useful existing behavior:

- `engine/adaptive_memory.py:12-17` already has categories like preferences, projects, current_tasks, corrections, successful_workflows, voice_preferences, model_preferences.
- `engine/adaptive_memory.py:129-145` ranks recalled memory by query token overlap and recency/use count.
- `engine/adaptive_memory.py:162-167` builds bounded memory context with `limit` and `max_chars`.
- `engine/memory/episodic_memory.py:74-124` stores task episodes safely and caps episodes to `max_episodes`.

Gap:

```txt
There is no rolling session summary manager that compresses older conversation beyond the last 10 exchanges.
There is no single context budget manager that combines rolling summary + last 10 exchanges + relevant long-term memories.
```

### 1.3 Existing voice/wake lifecycle pieces

Current relevant files:

```txt
engine/audio_wake_pipeline.py
engine/wake_session_manager.py
engine/runtime_bridge.py
engine/ui_state_manager.py
engine/command_bus.py
engine/interrupt_controller.py
engine/barge_in_manager.py
engine/tts_provider_manager.py
engine/groq_tts.py
engine/groq_asr.py
```

Observed details:

- `engine/audio_wake_pipeline.py:4-12` documents the intended flow: mic -> wake detection -> VAD command capture -> Groq Whisper -> runtime bridge/allCommands.
- `engine/audio_wake_pipeline.py:473-475` ignores wake detection when session detectors are paused.
- `engine/audio_wake_pipeline.py:581-655` captures one utterance using VAD, speech_started, silence, no-speech timeout, max duration.
- `engine/audio_wake_pipeline.py:727-751` runs ASR after capture and dispatches only final transcript.
- `engine/audio_wake_pipeline.py:753-760` states session persists through ASR + command + TTS and is finished by bridge.
- `engine/audio_wake_pipeline.py:783` starts a wake session.
- `engine/audio_wake_pipeline.py:845-864` finishes session on no speech / ASR empty.
- `engine/audio_wake_pipeline.py:865-874` intentionally keeps detectors paused after transcript dispatch when async bridge owns the lifecycle.
- `engine/wake_session_manager.py:49-79` starts a session, sets state `online`, and pauses detectors.
- `engine/wake_session_manager.py:106-137` finishes a session, sets state `sleep`, and resumes detectors.
- `engine/runtime_bridge.py:177-221` handles command dispatch and finishes session after command handling returns.
- `engine/runtime_bridge.py:46-73` maps bridge events to UI states.
- `engine/ui_state_manager.py:10-19` canonical states are currently `sleep`, `online`, `listening`, `waiting_for_speech`, `recognising`, `thinking`, `saying`, `error`.
- `engine/ui_state_manager.py:21-46` maps aliases like `speech_started`, `asr_started`, and `speaking` into those states.
- `engine/barge_in_manager.py:28-99` supports interrupting active speech and calls `groq_tts.stop()` / interrupt controller.
- `engine/interrupt_controller.py:41-50` tracks whether TTS is speaking.
- `engine/command_bus.py:61-70` interrupts current speech before a new command, but it does not yet enforce the stricter rule that full commands are only accepted in safe voice states.

Conclusion:

```txt
The wake pipeline already tries to avoid re-wake during ASR/TTS by pausing detectors, and tests already cover parts of this.
The missing upgrade is a strict, explicit VoiceState machine that gates command acceptance, UI state, ASR, TTS, cooldown, and barge-in behavior in one place.
```

### 1.4 Existing tests to reuse

Relevant test files already exist:

```txt
tests/test_session_memory.py
tests/test_memory_safety.py
tests/test_adaptive_memory.py
tests/test_memory_store.py
tests/test_episodic_memory.py
tests/test_semantic_memory.py
tests/test_gemini_memory_context.py

tests/test_audio_wake_pipeline.py
tests/test_wake_session_manager.py
tests/test_no_rewake_during_asr_tts.py
tests/test_no_rewake_during_recognising_thinking_saying.py
tests/test_detectors_pause_after_wake.py
tests/test_vad_waits_for_speech_after_wake.py
tests/test_tts_saying_then_sleeping.py
tests/test_ui_sleep_after_tts.py
tests/test_ui_saying_during_tts.py
tests/test_barge_in_manager.py
```

Notable existing test evidence:

- `tests/test_audio_wake_pipeline.py` contains a regression asserting the session stays active and detectors stay paused after transcript dispatch so the mic does not re-listen during thinking/speaking.
- `tests/test_barge_in_manager.py` already tests interrupt behavior when speaking.

New work should add tests around these, not replace them.

---

## 2. Web Research Findings

### 2.1 LangChain/LangGraph memory model

Source checked:

```txt
https://docs.langchain.com/oss/python/concepts/memory
```

Finding:

```txt
Short-term memory is thread/session-scoped state that tracks the ongoing conversation.
Long-term memory stores user/application data across sessions and can be recalled later.
```

This matches the desired Jarvis design:

```txt
short-term = latest 10 exchanges + rolling session summary
long-term = durable user preferences, plans, project facts, corrections
```

### 2.2 OpenAI Realtime VAD docs

Source checked:

```txt
https://developers.openai.com/api/docs/guides/realtime-vad
```

Finding:

```txt
When VAD is enabled, the system emits events indicating speech start and speech stop.
VAD can chunk audio based on silence or semantic completion.
```

This supports Jarvis using explicit states:

```txt
LISTENING -> RECORDING_UTTERANCE -> RECOGNIZING
```

### 2.3 Azure Speech single-shot recognition docs

Source checked:

```txt
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech
```

Finding:

```txt
Single-shot recognition recognizes one utterance.
The end of one utterance is determined by silence at the end or a maximum audio duration.
```

This supports using single-utterance command capture instead of uncontrolled continuous recognition.

### 2.4 LiveKit turn detection guidance

Source checked:

```txt
https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection
```

Finding:

```txt
Turn detection is a major latency point.
A silence timeout directly adds delay before the agent can respond.
```

This supports keeping VAD end-silence configurable and not too high.

---

## 3. Target Architecture

### 3.1 Memory layers

Use four layers:

```txt
Layer 1: Live turn
- current final user input
- current selected route/tool/result

Layer 2: Latest 10 exchanges
- raw but redacted user-assistant exchange pairs
- automatically updated every turn
- never requires the user to say “remember this”

Layer 3: Rolling session summary
- summary of older exchanges beyond the latest 10
- updated when exchange count exceeds the raw window
- max 800-1200 tokens/chars-equivalent budget

Layer 4: Long-term memory
- durable preferences, project facts, corrections, decisions, plans
- extracted selectively through memory candidate policy
- protected by safety filter
```

### 3.2 Memory flow

```txt
Final ASR transcript or typed text
↓
command_bus receives input
↓
add user turn to autonomous exchange buffer
↓
build context for router/brain:
  active voice state
  active workflow/followup
  rolling summary
  latest 10 exchanges
  top 3-5 long-term memories
↓
route and execute
↓
add assistant response to exchange buffer
↓
if raw exchanges > 10:
  summarize overflow into rolling summary
  keep latest 10 raw exchanges
↓
extract memory candidates
↓
safety filter
↓
store only high-value durable facts
```

### 3.3 Voice state machine

Target states:

```txt
SLEEPING
LISTENING
RECORDING_UTTERANCE
RECOGNIZING
THINKING
SPEAKING
COOLDOWN
```

Target lifecycle:

```txt
SLEEPING
  wake word / clap / hotkey / mic button
  ↓
LISTENING
  VAD waiting for speech
  ↓
RECORDING_UTTERANCE
  VAD speech_started; capture one utterance
  ↓
RECOGNIZING
  ASR running; no new full command accepted
  ↓
THINKING
  router / tool / brain running; no new full command accepted
  ↓
SPEAKING
  TTS output; no normal listening; only interrupt words allowed
  ↓
COOLDOWN
  500-1000ms; flush audio buffers
  ↓
SLEEPING or LISTENING depending wake mode/follow-up policy
```

Main invariant:

```txt
Normal full-command listening is allowed only in LISTENING and RECORDING_UTTERANCE.
```

Allowed exception:

```txt
During SPEAKING, only interrupt words are allowed:
stop, pause, cancel, sleep.
```

---

## 4. Implementation Plan

## Phase 1: Add canonical autonomous exchange memory

Objective:

```txt
Create one source of truth for latest 10 user-assistant exchanges and rolling summary.
```

Create:

```txt
engine/autonomous_memory.py
```

Core classes/functions:

```txt
Exchange
AutonomousExchangeMemory
get_autonomous_memory()
add_user_message(text, source, metadata=None)
add_assistant_message(text, source, metadata=None)
get_last_exchanges(limit=10)
get_rolling_summary()
build_context(user_text, max_chars)
clear_short_term()
```

Design details:

```txt
- Store exchanges as user+assistant pairs, not only individual turns.
- Keep exactly last_exchange_limit=10 completed exchanges raw.
- Maintain current incomplete exchange when user message arrives before assistant response.
- Sanitize all text through engine.memory_safety.redact_sensitive() and is_safe_to_store().
- Do not persist raw last-10 exchanges unless explicitly configured; default can be process memory.
- Rolling summary can persist to data/memory/session_summary.json if needed, but must not contain secrets.
```

Use existing code:

```txt
engine.memory_safety.redact_sensitive
engine.memory_safety.is_safe_to_store
engine.adaptive_memory.remember / recall
engine.memory_store.build_memory_context
```

Tests:

```txt
tests/test_autonomous_memory.py
```

Test cases:

```txt
- 11 exchanges leaves 10 raw exchanges.
- Oldest overflow is merged into rolling summary.
- Secret-looking text is blocked or redacted.
- build_context includes rolling summary + latest exchanges + relevant long-term memories.
- raw context size stays bounded.
```

---

## Phase 2: Integrate autonomous memory with command bus and assistant responses

Objective:

```txt
Store final user transcripts and final assistant responses automatically.
```

Modify:

```txt
engine/command_bus.py
engine/command.py
engine/conversation_context.py
```

Plan:

1. In `engine/command_bus.py:35-58`, after transcript cleaning/finalization, add final user text to autonomous memory.
2. Avoid storing partial ASR events. Only store text after final ASR result becomes command text.
3. In the central assistant response path, add final assistant response to autonomous memory.
4. Keep existing `engine.conversation_context.add_user_turn()` for compatibility, but make the new autonomous memory the preferred context source.
5. Avoid double-storing if a response path calls both `_respond_to_user()` and `speak()`.

Potential integration points for assistant response:

```txt
engine/command.py::_store_conversation_turn()
engine/command.py::_respond_to_user()
engine/command.py::speak()
```

Research note:

```txt
Find the least duplicated point before implementation. The preferred point is _store_conversation_turn() if every final command path uses it exactly once.
```

Tests:

```txt
tests/test_autonomous_memory_integration.py
```

Test cases:

```txt
- command_bus stores a user turn once.
- assistant response stores assistant turn once.
- “what were we discussing?” can retrieve latest exchange context.
- final ASR transcript is stored, but asr_started/speech_started status text is not stored.
```

---

## Phase 3: Add rolling summary manager

Objective:

```txt
Compress older conversation beyond the latest 10 exchanges.
```

Create:

```txt
engine/session_summary_manager.py
```

Core functions:

```txt
get_summary()
merge_exchange(exchange)
merge_exchanges(exchanges)
summarize_if_needed(memory)
reset_summary()
to_context(max_chars=1600)
```

Implementation options:

```txt
Option A, deterministic first:
- use extractive bullet summary from old turns
- keep facts/plans/decisions/errors/next steps
- no model call required

Option B, optional LLM summary:
- only if configured
- use cheap model
- never include secrets
```

Recommended first implementation:

```txt
Use deterministic summary first.
Do not add a cloud summarizer until tests pass.
```

Summary should keep:

```txt
current task
current plan
important decisions
selected feature/tool
recent errors
failed attempts
successful fixes
pending next steps
user corrections/preferences
```

Summary should drop:

```txt
small talk
transient logs
large code dumps
sensitive text
repeated status messages
```

Tests:

```txt
tests/test_session_summary_manager.py
```

---

## Phase 4: Add memory candidate extractor and long-term safety gate

Objective:

```txt
Evolve over time without saving everything permanently.
```

Create or extend:

```txt
engine/memory_candidate_extractor.py
engine/adaptive_memory.py
engine/memory_safety.py
```

Candidate categories:

```txt
identity
preferences
projects
current_tasks
corrections
voice_preferences
model_preferences
file_preferences
successful_workflows
tool_failures
implementation_decisions
pending_next_steps
```

Candidate scoring:

```txt
0.90+ explicit preference/correction/project rule -> store
0.75+ implementation decision or stable plan -> store if safe
0.50-0.74 keep only in rolling summary
below 0.50 ignore
```

Never store permanently:

```txt
passwords
OTP
API keys
tokens
cookies
private keys
credit card data
sensitive screen text
large code dumps
raw logs
```

Modify:

```txt
engine/adaptive_memory.py::maybe_extract_memory()
```

Current extractor only responds to trigger phrases. Upgrade it to evaluate completed exchanges, but still store only high-value durable items.

Tests:

```txt
tests/test_memory_candidate_extractor.py
tests/test_memory_safety.py
```

---

## Phase 5: Add context budget manager

Objective:

```txt
Ensure context is useful but token-efficient.
```

Create:

```txt
engine/context_budget_manager.py
```

Context build order:

```txt
1. active mode/state
2. pending workflow/followup/clarification
3. relevant long-term memory, top 3-5
4. rolling summary, max 800-1200 tokens/chars-equivalent
5. latest 10 exchanges, compact and trimmed
6. current user input
7. compact tool manifest only when routing needs it
```

Modify:

```txt
engine/intent_context_builder.py
engine/gemini_brain.py
engine/groq_intent_router_v2.py
```

Current issue:

```txt
engine/intent_context_builder.py currently sends only 4 recent turns. Replace with compact autonomous memory context while preserving small router payload.
```

Config defaults:

```txt
JARVIS_LAST_EXCHANGE_LIMIT=10
JARVIS_ROLLING_SUMMARY_MAX_CHARS=5000
JARVIS_CONTEXT_MAX_CHARS=8000
JARVIS_LONG_TERM_MEMORY_LIMIT=5
JARVIS_RECENT_EXCHANGE_MAX_CHARS=4500
```

Tests:

```txt
tests/test_context_budget_manager.py
```

---

## Phase 6: Add explicit voice state machine

Objective:

```txt
Make voice lifecycle explicit and enforceable.
```

Create:

```txt
engine/voice_state_machine.py
```

States:

```txt
SLEEPING
LISTENING
RECORDING_UTTERANCE
RECOGNIZING
THINKING
SPEAKING
COOLDOWN
ERROR
```

Core API:

```txt
get_voice_state_machine()
transition(event, source='', session_id='', metadata=None)
get_state()
can_accept_full_command()
can_accept_interrupt()
require_state(expected)
mark_sleeping()
mark_listening()
mark_recording()
mark_recognizing()
mark_thinking()
mark_speaking()
mark_cooldown()
```

Allowed transitions:

```txt
SLEEPING -> LISTENING on wake_detected
LISTENING -> RECORDING_UTTERANCE on speech_started
RECORDING_UTTERANCE -> RECOGNIZING on speech_ended/asr_started
RECOGNIZING -> THINKING on transcript_final
THINKING -> SPEAKING on tts_started
SPEAKING -> COOLDOWN on tts_finished/interrupted
COOLDOWN -> SLEEPING or LISTENING after cooldown_complete
ANY -> SLEEPING on sleep/cancel/error/session_finish
```

State gate:

```txt
can_accept_full_command() == True only for LISTENING/RECORDING_UTTERANCE and typed UI commands.
voice command_bus input from mic/hotword is rejected/deferred otherwise.
can_accept_interrupt() == True during SPEAKING for stop/pause/cancel/sleep.
```

Tests:

```txt
tests/test_voice_state_machine.py
```

---

## Phase 7: Integrate state machine into wake pipeline and bridge

Objective:

```txt
Wire actual runtime events to the state machine.
```

Modify:

```txt
engine/audio_wake_pipeline.py
engine/runtime_bridge.py
engine/wake_session_manager.py
engine/ui_state_manager.py
```

Integration points:

```txt
wake detected              -> LISTENING
capture_command start      -> LISTENING
speech_started             -> RECORDING_UTTERANCE
speech_ended/asr_started   -> RECOGNIZING
asr_result nonempty        -> THINKING
command dispatch started   -> THINKING
speak started              -> SPEAKING
speak finished             -> COOLDOWN
cooldown done              -> SLEEPING or LISTENING
session finish/error       -> SLEEPING
```

Important current mapping to preserve:

```txt
runtime_bridge.STATUS_TO_UI_STATE maps speech_started/asr_started to recognising.
ui_state_manager maps canonical states to old UI labels.
Old legacy UI must still work through eel.updateJarvisState().
```

Add COOLDOWN carefully:

```txt
- It can be internal-only at first.
- UI may show `sleep` or a new `cooldown` label later.
- Do not break existing UI tests that expect sleep after TTS.
```

Tests:

```txt
tests/test_voice_state_machine_bridge.py
tests/test_no_rewake_during_recognising_thinking_saying.py
tests/test_no_rewake_during_asr_tts.py
tests/test_audio_wake_pipeline.py
```

---

## Phase 8: Add TTS lock and post-TTS cooldown

Objective:

```txt
Prevent Jarvis from hearing itself and starting a new command during/just after TTS.
```

Modify:

```txt
engine/command.py
engine/tts_provider_manager.py
engine/groq_tts.py
engine/interrupt_controller.py
engine/barge_in_manager.py
engine/audio_wake_pipeline.py
```

Plan:

1. When `speak()` starts, transition to SPEAKING and set `interrupt_controller.set_speaking(True)`.
2. During SPEAKING, full command acceptance is off.
3. Only interrupt words are accepted from voice:

```txt
stop
pause
cancel
sleep
```

4. When TTS ends or is interrupted, transition to COOLDOWN.
5. In COOLDOWN, drain/flush wake audio frames for 500-1000 ms.
6. After cooldown, transition to SLEEPING or LISTENING according to follow-up policy.

Config:

```txt
JARVIS_POST_TTS_COOLDOWN_MS=800
JARVIS_BARGE_IN_WORDS=stop,pause,cancel,sleep
```

Tests:

```txt
tests/test_tts_lock_and_cooldown.py
tests/test_barge_in_manager.py
tests/test_ui_sleep_after_tts.py
```

---

## Phase 9: Command acceptance gate

Objective:

```txt
Make sure recognition/thinking/speaking cannot create second accidental commands.
```

Modify:

```txt
engine/command_bus.py
engine/runtime_bridge.py
```

Policy:

```txt
Typed UI commands can still be accepted unless explicitly blocked.
Voice commands from hotword/clap/mic should respect voice state.
During RECOGNIZING/THINKING/COOLDOWN, reject or ignore voice full commands.
During SPEAKING, accept only interrupt words.
```

Pseudo-flow:

```txt
if mode == 'voice':
    if voice_state == SPEAKING and text in barge_in_words:
        interrupt_tts()
        return True
    if not voice_state.can_accept_full_command():
        log '[VOICE_STATE] command_ignored state=...'
        return False
```

Tests:

```txt
tests/test_voice_command_gate.py
```

Test cases:

```txt
- voice command during RECOGNIZING is ignored.
- voice command during THINKING is ignored.
- voice command during SPEAKING is ignored unless it is stop/pause/cancel/sleep.
- `stop` during SPEAKING interrupts TTS.
- typed command still works if allowed by UI mode.
```

---

## Phase 10: UI clarity

Objective:

```txt
Make status visible and non-confusing.
```

Modify:

```txt
engine/ui_state_manager.py
engine/runtime_bridge.py
www/controller.js
www/style.css only if necessary
```

Display states:

```txt
Sleeping
Listening
Recording...
Recognizing...
Thinking...
Speaking...
Cooldown / Paused
```

Current UI states:

```txt
sleep
online
listening
waiting_for_speech
recognising
thinking
saying
error
```

Recommended UI-compatible mapping:

```txt
SLEEPING             -> sleep
LISTENING            -> listening or waiting_for_speech
RECORDING_UTTERANCE  -> recognising with label RECORDING... or new recording state
RECOGNIZING          -> recognising
THINKING             -> thinking
SPEAKING             -> saying
COOLDOWN             -> sleep or new cooldown state after tests are updated
```

Do not redesign UI. Only add state labels if needed.

Optional debug fields:

```txt
last command heard
selected intent
selected feature
confidence
memory used yes/no
voice state
```

---

## Phase 11: Acceptance tests

Add or extend these tests:

```txt
tests/test_autonomous_memory.py
tests/test_session_summary_manager.py
tests/test_context_budget_manager.py
tests/test_memory_candidate_extractor.py
tests/test_voice_state_machine.py
tests/test_voice_command_gate.py
tests/test_tts_lock_and_cooldown.py
tests/test_voice_memory_integration.py
```

Required acceptance cases:

```txt
1. User completes 11 exchanges; latest 10 remain raw and older turns are summarized.
2. User asks “what were we discussing?” and Jarvis answers from recent context.
3. User says “go to sleep”; normal voice commands are ignored until wake.
4. During RECOGNIZING, new voice audio cannot create a second command.
5. During THINKING, new voice audio cannot create a second command.
6. During SPEAKING, Jarvis does not hear itself as a normal command.
7. “stop” during SPEAKING interrupts TTS.
8. After TTS cooldown, detectors/listening resume cleanly.
9. Token/context budget remains bounded.
10. Secrets are not saved in raw exchanges, rolling summary, or long-term memory.
```

---

## 5. Best Defaults

```txt
JARVIS_LAST_EXCHANGE_LIMIT=10
JARVIS_ROLLING_SUMMARY_MAX_CHARS=5000
JARVIS_CONTEXT_MAX_CHARS=8000
JARVIS_LONG_TERM_MEMORY_LIMIT=5
JARVIS_RECENT_EXCHANGE_MAX_CHARS=4500
JARVIS_POST_TTS_COOLDOWN_MS=800
JARVIS_BARGE_IN_WORDS=stop,pause,cancel,sleep
ASR_MODE=single_utterance
VAD_SILENCE_END_MS=900 to 1200 for quick command mode
ASR_MAX_RECORD_SECONDS=25
NO_SPEECH_TIMEOUT_MS=15000
```

Need to preserve current wake defaults from repo context unless deliberately changed:

```txt
POST_WAKE_DELAY_MS=800
NO_SPEECH_TIMEOUT_MS=15000
END_SILENCE_MS=1800
VAD_MIN_SPEECH_MS=400
ASR_MIN_AUDIO_MS=1200
MAX_RECORD_SECONDS=25
```

---

## 6. Verification Commands

Focused memory tests:

```bash
.venv\Scripts\python.exe -m pytest tests/test_autonomous_memory.py tests/test_session_summary_manager.py tests/test_context_budget_manager.py tests/test_memory_candidate_extractor.py -v
```

Existing memory regression tests:

```bash
.venv\Scripts\python.exe -m pytest tests/test_session_memory.py tests/test_memory_safety.py tests/test_adaptive_memory.py tests/test_memory_store.py tests/test_episodic_memory.py tests/test_semantic_memory.py -v
```

Focused voice tests:

```bash
.venv\Scripts\python.exe -m pytest tests/test_voice_state_machine.py tests/test_voice_command_gate.py tests/test_tts_lock_and_cooldown.py tests/test_barge_in_manager.py -v
```

Existing wake/TTS regression tests:

```bash
.venv\Scripts\python.exe -m pytest tests/test_audio_wake_pipeline.py tests/test_wake_session_manager.py tests/test_no_rewake_during_asr_tts.py tests/test_no_rewake_during_recognising_thinking_saying.py tests/test_detectors_pause_after_wake.py tests/test_tts_saying_then_sleeping.py tests/test_ui_sleep_after_tts.py -v
```

Safety and syntax:

```bash
.venv\Scripts\python.exe scripts/verify_safety.py
.venv\Scripts\python.exe -m compileall src engine
```

Full suite when stable:

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

Live validation, only after tests pass:

```bash
.venv\Scripts\python.exe run.py
```

Manual live checks:

```txt
- Wake with hotword/clap.
- Speak one command.
- Confirm UI state order is clear.
- Confirm it does not listen during recognizing/thinking/speaking.
- Say “stop” during TTS and confirm TTS stops.
- After cooldown, wake/listening works again.
- Ask “what were we just discussing?” after 10+ turns.
```

---

## 7. Risks and Guardrails

### Risk: duplicate memory writes

Mitigation:

```txt
Use one central integration point for user messages and one for assistant messages.
Add tests that count exchanges.
```

### Risk: permanent memory pollution

Mitigation:

```txt
Keep latest 10 exchanges short-term only.
Only high-confidence durable candidates go to long-term memory.
Use memory safety filter before summary and before storage.
```

### Risk: breaking existing wake flow

Mitigation:

```txt
Do not bypass audio_wake_pipeline, runtime_bridge, command_bus, or wake_session_manager.
Add state machine as coordinator, not rewrite.
Preserve existing tests around no re-wake during ASR/TTS.
```

### Risk: UI tests expecting old states

Mitigation:

```txt
Map new internal states to existing UI states first.
Only add visible new UI states after old state tests are updated.
```

### Risk: TTS cooldown feels slow

Mitigation:

```txt
Make cooldown configurable.
Default 800ms.
Allow 500ms for faster command mode if live tests are clean.
```

---

## 8. Final Build Order

Recommended implementation order:

```txt
1. engine/autonomous_memory.py + tests
2. engine/session_summary_manager.py + tests
3. engine/context_budget_manager.py + tests
4. command_bus / command integration for automatic exchange writes
5. memory candidate extractor upgrade
6. engine/voice_state_machine.py + tests
7. wire audio_wake_pipeline/runtime_bridge/ui_state_manager to voice state
8. add TTS lock + cooldown
9. add voice command gate
10. run full memory + wake + TTS regression suite
11. live run.py validation
```

Final verdict:

```txt
Build Autonomous Last-10 Exchange Memory + Rolling Summary + Strict Voice State Machine.
Use existing Jarvis memory and wake modules, but add one canonical layer that makes the behavior explicit, token-efficient, and testable.
```
