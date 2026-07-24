# Autonomy Execution Readiness — Verified

## Current State: 4/10

The system can execute commands reliably but cannot chain them autonomously. Readiness is scored on 5 dimensions:

### 1. Wake → ASR → Command (Score: 9/10)
- openWakeWord detection ✅
- Silero VAD with noise rejection ✅
- Groq Whisper ASR ✅
- Pipeline session management ✅
- 2 pipeline-disabled test failures (minor)

### 2. Intent Routing (Score: 8/10)
- 14 route types with slot validation ✅
- LLM fallback for ambiguous input ✅
- Confidence scoring ✅
- Missing slot detection with clarification ✅
- Pre-routing intercepts some commands (workflow dialog, memory, output run BEFORE v2) ⚠️
- No ReAct handler despite route support ❌

### 3. Follow-up Chaining (Score: 2/10)
- `_mark_question_response()` detects questions ✅
- `turn_manager` tracks auto-listen requests ✅
- `followup_manager` resolves answers ✅
- **BUT**: default env var = false ❌
- **BUT**: uses legacy `takecommand()` ❌
- **BUT**: missing "double_clap" in `_FOLLOWUP_SOURCES` ❌
- **BUT**: bridge sleep races auto-follow-up ❌

### 4. Brain Output Control (Score: 1/10)
- Gemini output goes to TTS unchanged ❌
- No structured output classification ❌
- No safety filter on brain output ❌
- No action detection from brain suggestions ❌
- No confidence assessment on brain responses ❌

### 5. Agency Background Execution (Score: 5/10)
- 6-pass workflow engine exists ✅
- Tool proxy with approval gate ✅
- Background thread execution ✅
- JSONL persistence ✅
- **BUT**: disabled by default ❌
- **BUT**: not documented ❌
- **BUT**: single-workflow limit ⚠️

## What It Takes to Reach 9/10

```
Set NEXI_AUTO_FOLLOWUP_AFTER_TTS=true            → +3 (follow-up chaining)
Wire _maybe_start_auto_followup through command_bus → +2 (modern pipeline)
Add post-brain classifier                          → +3 (brain output control)
Add "double_clap" to _FOLLOWUP_SOURCES            → +1 (clap follow-up)
Add NEXI_AGENCY_AUTONOMY to .env.example          → +1 (agency discoverability)
Add react handler to _handle_product_intelligence_v2 → +1 (multi-step tasks)
```

After these 6 changes: **9/10 readiness**.
