# Router & Follow-up Gap Report — Verified

## Core Problem: Three Half-Connected Pipelines

### Pipeline 1: Modern Wake → ASR → Bridge → Command Bus
```
audio_wake_pipeline → post_command(queue, text)
  → [multiprocessing.Queue]
  → runtime_bridge.handle_bridge_event(event)
    → submit_user_command(text, source="hotword", mode="voice")
      → command_bus.py (followup manager, clarification, transcript filter)
        → dispatch_unified_command()
          → allCommands() → router v2 → tool/brain → speak()
```

Status: **WORKS** — This is the modern, reliable pipeline. Uses VAD + Groq Whisper.

### Pipeline 2: Bridge → Post-TTS Sleep
```
speak() finishes → _set_ui_state("sleep", ...)
  → _finish_session()  [runtime_bridge.py:215-218]
    → wake_session_manager.finish_session("complete")
      → session lock released → wake detectors resume
```

Status: **BROKEN BY DEFAULT** — `NEXI_AUTO_FOLLOWUP_AFTER_TTS=false` means session dies after every response. Even when set to `true`, there's another problem:

### Pipeline 3: Follow-up Auto-Listen → Legacy `takecommand()`
```
_maybe_start_auto_followup()  [command.py:502-525]
  → checks _FOLLOWUP_SOURCES  [line 514]
    → "double_clap" source is NOT in _FOLLOWUP_SOURCES!  [line 482]
  → consume_auto_listen_request()
  → _set_ui_state("listening")
  → takecommand()  ← LEGACY SpeechRecognition, NOT modern VAD/Groq!
  → submit_user_command(query, source=source, mode="voice")
```

Status: **BROKEN** — Uses legacy SpeechRecognition (`takecommand()`) instead of modern wake pipeline (VAD + Groq ASR). Also, source "double_clap" is missing from `_FOLLOWUP_SOURCES`.

## Follow-up Flow — Step-by-Step Verification

### Scenario: "open up" → "Chrome"

**Step 1: "open up"**
1. `command_bus.submit_user_command("open up")` → `dispatch_unified_command("open up")` → `allCommands("open up")`
2. Pre-routing checks pass (not emergency, not stop, not wake/sleep, not diagnostic, not cognitive, not clarification, not workflow)
3. Router v2: `_deterministic_router("open up")` → `route="clarify", intent="open_app", missing_slots=["app_name"]` (line 341-342)
4. `_handle_product_intelligence_v2()` → route="clarify" + intent="open_app" → calls `_respond_to_user("Which app should I open?")` (line 828)
5. `_respond_to_user()` → `_response_expects_user_reply()` (line 548) → `response_asks_question("Which app?")` → ends with `?` → True
6. `ask_user()` → `speak("Which app should I open?")`
7. `speak()` → `_mark_question_response("Which app?")` → detects question → sets pending followup
8. `turn_manager.mark_waiting_for_user()` → `_auto_listen_requested = True`
9. After TTS: `_set_ui_state("listening" if expects_followup else "sleep")` → True → "listening"
10. `_maybe_start_auto_followup()` → checks `_FOLLOWUP_SOURCES` → source is typically "typed" or "hotword" → OK if in set
11. → `takecommand()` → **legacy SpeechRecognition**
12. Query "Chrome" → `submit_user_command("Chrome", source=source, mode="voice")`

**Step 2: "Chrome"**
1. `command_bus.submit_user_command("Chrome")` → checks pending followup → `consume_followup_answer("Chrome")`
2. `_route_pending_answer("open_app", "Chrome")` → returns `("open Chrome", "local_skill")`
3. `normalized = "open Chrome"`
4. Router v2: `_deterministic_router("open Chrome")` → opens Chrome
5. ✅ Opens Chrome

**BUT**: If `NEXI_AUTO_FOLLOWUP_AFTER_TTS` is `false` (default), the bridge path (runtime_bridge.py:213-215) calls `_finish_session()` which kills the session. The auto-followup in `speak()` still runs (it's in the same process), so step 10 still executes. But the session lock is released, potentially causing race conditions with new wake detections.

### Gap: Double-clap source not in _FOLLOWUP_SOURCES

`command.py:482`: `_FOLLOWUP_SOURCES = {"hotword", "clap", "hotkey", "ui_button", "mic_button", "voice"}`

Missing `"double_clap"`. The pipeline sends `source="double_clap"` (from audio_wake_pipeline). When auto-followup checks `if source not in _FOLLOWUP_SOURCES: return`, double-clap-initiated sessions will NOT enter follow-up listening.

### Gap: Post-TTS bridge sleep wins over follow-up

`runtime_bridge.py:207-215`:
```python
auto_followup = (os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "false") ...)
if auto_followup and (has_pending_followup() or has_pending_clarification()):
    _set_ui_state("listening", ...)
else:
    _set_ui_state("sleep", ...)
    _finish_session()
```

When `auto_followup=False` (default): bridge ALWAYS sleeps after command. The `speak()` path's `_maybe_start_auto_followup()` may still run (it's in the same process) but the bridge's `_finish_session()` at line 215 releases the session lock. This allows new wake detections to interrupt the follow-up.

## Summary of Router Defects

1. **No post-brain classifier** — brain output goes straight to TTS
2. **ReAct planner exists but no handler** — router identifies react intent but command.py has no case for it
3. **`_FOLLOWUP_SOURCES` missing `"double_clap"`** — double clap wakes can't auto-follow-up
4. **Follow-up uses legacy `takecommand()`** — not modern VAD/Groq pipeline
5. **`NEXI_AUTO_FOLLOWUP_AFTER_TTS` not in `.env.example`** — users never get follow-up
6. **`AUTO_LISTEN_AFTER_QUESTION` vs `NEXI_AUTO_FOLLOWUP_AFTER_TTS` confusion** — two different env vars for similar concepts
