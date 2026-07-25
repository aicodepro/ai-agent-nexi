# Dialogue State & Follow-up Listening Audit

## CRITICAL FINDING: Follow-up is BROKEN by default

The `runtime_bridge.py` at line 207-208 has:
```python
auto_followup = (os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "false") or "").strip().lower() in {"1", "true", "yes", "on"}
```

**Default is `false`**. This means after every command → TTS → sleep. No follow-up listening by default.

However, there IS a second follow-up mechanism in `command.py` via `_maybe_start_auto_followup()`.

## Follow-up Mechanism #1: `speak()` → `_maybe_start_auto_followup()`

File: `engine/command.py:277-369`

When `speak()` is called:
- Line 309: `_mark_question_response()` — checks if response expects user reply
- Line 312: `should_auto_listen()` — checks turn_manager state
- If either is True, `expects_followup = True`
- Line 364: After TTS, `_set_ui_state("listening" if expects_followup else "sleep")`
- Line 368-369: If `expects_followup`, calls `_maybe_start_auto_followup()`

### `_mark_question_response()` — command.py:166-206

Uses `response_asks_question()` from `assistant_response.py:41`:
- Checks if text ends with `?`
- Checks if text starts with question words (what, which, where, etc.)
- Excludes rhetorical phrases

If question detected:
1. Sets pending followup via `followup_manager.set_pending_followup()`
2. Calls `turn_manager.mark_waiting_for_user()` — sets `_auto_listen_requested = True`

### `_maybe_start_auto_followup()` — command.py:502-525

1. Checks `turn_manager.should_auto_listen()` — True if `_auto_listen_requested`
2. Consumes the request
3. Calls `_set_ui_state("listening")`
4. Calls `takecommand()` — **BLOCKING CALL using legacy SpeechRecognition**
5. If query returned, calls `submit_user_command(query, source=followup_source, mode="voice")`

## Follow-up Mechanism #2: `runtime_bridge.py` auto_followup

File: `engine/runtime_bridge.py:207-216`

After `submit_user_command()` returns:
- Checks `NEXI_AUTO_FOLLOWUP_AFTER_TTS` env var (default: false)
- If enabled, checks for pending followup/clarification and sets state to "listening"
- Otherwise: goes to sleep and calls `_finish_session()`

## Case Analysis

### Case 1: "open up"
- Router: `_deterministic_router()` at line 341 → `route="clarify", intent="open_app", missing_slots=["app_name"]`
- `_handle_product_intelligence_v2()` route `clarify` + intent `open_app` → handles at line 828 with `_respond_to_user(response, reason="missing_slot")` → `speak("Which app should I open?")`
- In `speak()`, `_mark_question_response()` → `response_asks_question("Which app?")` → True (ends with ?)
- `turn_manager.mark_waiting_for_user()` → `_auto_listen_requested = True`
- After TTS, `_set_ui_state("listening")` → calls `_maybe_start_auto_followup()` → `takecommand()`
- **BUT**: `_maybe_start_auto_followup()` checks `current_source()` and if not in `_FOLLOWUP_SOURCES` (which includes voice), it returns early. Since the source is set by `command_bus.submit_user_command()`, this depends on context.

### Case 2: User says "Chrome" after system asks "Which app?"
- `_maybe_start_auto_followup()`'s `takecommand()` returns "chrome"
- `submit_user_command("chrome", source="voice", mode="voice")` → `dispatch_unified_command("chrome")`
- `command_bus.submit_user_command()` at line 231-254 checks `pending_followup = has_pending_followup()`
- If pending, `consume_followup_answer()` at line 244 routes through `followup_manager.py`
- `followup_manager.consume_followup_answer("chrome")` → `_route_pending_answer("open_app", "chrome")` → returns `("open chrome", "local_skill")`
- `normalized` becomes `"open chrome"`, which then goes through `_handle_product_intelligence_v2()` → `open_app` with slot `app_name=chrome`

### Case 3: "create a folder called reports"
- Router: route="workflow", intent="create_folder"
- `start_create_folder()` detects name="reports", no location
- Returns "Where should I create reports?"
- `_respond_to_user()` → `speak()` → `_mark_question_response()` → question detected → auto-followup

### Case 4: User says "Desktop" after "Where should I create reports?"
- Via _maybe_start_auto_followup → `submit_user_command("desktop")` → `command_bus` checks pending workflow → `workflow_state.has_active_workflow()` → True → workflow dialog handles it via `handle_workflow_turn()` in allCommands (line 1826)
- Wait, no — the workflow_dialog_manager runs at line 1826 in allCommands. But submit_user_command goes through dispatch_unified_command → allCommands. In allCommands, workflow_dialog_manager is step 7, which runs BEFORE _handle_product_intelligence_v2 (step 10). So workflow takes priority.

### Case 5: "let's plan something"
- Router: `_deterministic_router()` doesn't match any pattern → falls through to LLM → or `no_feature_fallback` at line 422 with route="brain"
- Goes to `chatBot()` → Gemini answers → `speak()` → if Gemini ends its response with "?", it's detected as question → follow-up triggered

### Case 6: User says "plan my AI assistant demo" after "What should I plan?"
- Via follow-up mechanism → same as case 2

## Defects

1. **`NEXI_AUTO_FOLLOWUP_AFTER_TTS=false` by default** — The bridge path (runtime_bridge.py:207) goes to sleep after every command unless this is true. The `_maybe_start_auto_followup()` path still works regardless, but the bridge path will call `_finish_session()` which may interfere.

2. **`_maybe_start_auto_followup()` uses legacy `takecommand()`** — This is the SpeechRecognition-based path, NOT the modern wake pipeline. It opens a new mic stream, doesn't go through VAD/energy detection, and may behave differently.

3. **Followup source gating is narrow** — `_FOLLOWUP_SOURCES` at line 482 includes only `{"hotword", "clap", "hotkey", "ui_button", "mic_button", "voice"}`. If the source is anything else (e.g., "bridge", "clarification"), auto-followup is skipped.

4. **Session finish race** — The bridge path at line 214-215 calls `_finish_session()` after every command by default. If follow-up is pending, this kills the session. The auto-followup path in `speak()` also calls `_finish_session()` but only if `expects_followup` is False.

5. **No per-turn dialogue state for slot filling** — The `workflow_state.py` supports single active workflow. But there's no general-purpose `DialogueState` object that tracks pending route, pending slots, and intent across turns. The followup mechanism handles this partially but it's not a first-class abstraction.

6. **LLM brain output has no classification** — Post-brain output is classified only by `response_asks_question()` (text-based `?` check). There's no structured output from Gemini indicating intent (final_answer, needs_user_input, suggested_feature, etc.).
