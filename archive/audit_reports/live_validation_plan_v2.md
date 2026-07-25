# Live Validation Plan v2 — Verified

## Before Testing

Ensure `.env` contains:
```
NEXI_AUTO_FOLLOWUP_AFTER_TTS=true     ← CRITICAL for follow-up
NEXI_INTENT_V2_ENABLED=true           ← Must be true
NEXI_AGENCY_AUTONOMY=true             ← For agency engine
GEMINI_API_KEY=<key>                  ← For brain
GROQ_API_KEY=<key>                    ← For ASR + TTS + router
```

## Validation Scenarios

### Scenario 1: Basic Wake → Command
**Command**: "Hey Nexi, what time is it?"
**Expected Route**: `tool → tell_time`
**Expected State Chain**: online → listening → recognising → thinking → saying → sleeping (or listening if auto_followup on)
**Verification**: Speaks the time. If `NEXI_AUTO_FOLLOWUP_AFTER_TTS=true`, stays listening.

### Scenario 2: Clarification → Follow-up
**Command**: "Hey Nexi, open up"
**Expected Route**: `clarify → open_app, missing_slots=["app_name"]`
**Expected Question**: "Which app should I open?"
**After Question**: Auto-listen should be active
**Follow-up Command**: "Chrome"
**Expected Route**: `tool → open_app, app_name=chrome`
**Verification**: Chrome opens

### Scenario 3: Workflow → Slot Fill
**Command**: "Hey Nexi, create a folder"
**Expected Route**: `workflow → create_folder`
**Expected Question**: "What should I name it?"
**Follow-up**: "reports"
**Verification**: Folder created on Desktop

### Scenario 4: Brain Q&A with Follow-up
**Command**: "Hey Nexi, what's the capital of France?"
**Expected Route**: `brain → general_qa`
**Verification**: Gemini answers "Paris." If response ends with "?", system should auto-listen.

### Scenario 5: Brain Question → Answer
**Command**: "Hey Nexi, do you know Python?"
**Expected Route**: `brain → general_qa` (or `system` depending on matching)
**Verification**: Gemini answers. If answer contains "?", auto-follow-up should activate.

### Scenario 6: Consecutive Commands
**Command 1**: "Hey Nexi, search for AI news"
**Expected**: Opens browser with search results
**After TTS**: Should stay listening (if auto_followup=true)
**Command 2**: "How about machine learning?"
**Expected**: New search or follow-up search
**Verification**: Commands chain without re-waking

### Scenario 7: High-Risk Action with Approval
**Command**: "Hey Nexi, type out hello world"
**Expected Route**: `tool → type_text, text="hello world"`
**Expected**: Risk=high, requires approval
**Verification**: UI shows pending approval
**Follow-up**: System waits for "approve" or "reject"

### Scenario 8: Agency Workflow
**Command**: "Hey Nexi, run an agent audit of the intent router"
**Expected Route**: `tool → nexi_run_router_audit`
**Verification**: Workflow starts. "Show current agent activity" reports progress.

### Scenario 9: Feature Gap
**Command**: "Hey Nexi, build a monitor that watches my downloads"
**Expected Route**: `tool → request_feature` (via _feature_gap_match at line 193-204)
**Verification**: "I'll log a feature request for..."

### Scenario 10: Interruption
**Command**: "Hey Nexi, tell me about quantum physics"
**During TTS**: "Stop"
**Expected**: TTS stops immediately, system sleeps

## Test Matrix

| Scenario | Command | Expected Route | Follow-up | Risk |
|----------|---------|---------------|-----------|------|
| 1 | "what time is it" | tool/tell_time | auto-listen if env=true | none |
| 2a | "open up" | clarify/open_app | auto-listen | none |
| 2b | "Chrome" | tool/open_app | sleep | none |
| 3a | "create a folder" | workflow/create_folder | auto-listen | none |
| 3b | "reports" | workflow/create_folder | sleep | none |
| 4 | "capital of France" | brain/general_qa | auto-listen if ? | none |
| 5 | "do you know Python" | brain/general_qa | auto-listen if ? | none |
| 6a | "search for AI news" | tool/web_search | auto-listen | none |
| 6b | "machine learning" | tool/web_search | sleep | none |
| 7 | "type out hello world" | tool/type_text | approval needed | high |
| 8 | "run an agent audit" | tool/nexi_run_router_audit | workflow start | low |
| 9 | "build a monitor..." | tool/request_feature | sleep | none |
| 10 | "tell me about quantum" | brain/general_qa → "stop" | interrupt | none |
