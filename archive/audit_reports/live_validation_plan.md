# Live Validation Plan

## Pre-Launch Checks

### 1. Environment Configuration
- [ ] Copy `.env.example` to `.env` with `NEXI_INTENT_V2_ENABLED=true`
- [ ] Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` (brain default)
- [ ] Set `GROQ_API_KEY` (ASR + TTS + LLM router default)
- [ ] Set `NEXI_AGENCY_AUTONOMY=true` (enable agency engine tools)
- [ ] Set `NEXI_AUTO_FOLLOWUP_AFTER_TTS=true` (enable follow-up bridge path)
- [ ] Set `OPENWAKEWORD_SCORE_THRESHOLD=0.25`, `CONSECUTIVE_HITS=1`
- [ ] Set `JARVIS_CLAP_PRIMARY=dsp_clap`, `JARVIS_CLAP_BACKEND_ORDER=dsp_clap,clap_nn`

### 2. Syntax Check
```bash
python -m compileall engine
```
Should pass without errors.

### 3. Test Suite
```bash
python -m pytest tests/ -v --timeout=60 2>&1 | tail -50
```
Target: ≥90% pass rate. Known failures documented.

## Validation Scenarios

### Scenario 1: Wake → Command
1. Say "Hey Nexi" (or double-clap)
2. Expected: UI shows "online" state
3. Say "What time is it?"
4. Expected: UI shows "listening" → "recognising" → "thinking" → "saying" → "sleeping"
5. System should speak the time

### Scenario 2: Clarification → Follow-up
1. Say "Hey Nexi, open"
2. Expected: System asks "Which app should I open?"
3. Expected: Auto-followup starts (listening state)
4. Say "Chrome"
5. Expected: Chrome opens

### Scenario 3: Multi-turn Slot Filling
1. Say "Hey Nexi, create a new folder"
2. Expected: System asks for name
3. Say "reports"
4. Expected: System asks for location (or creates in Desktop)
5. Confirm folder created

### Scenario 4: Brain Q&A with Follow-up
1. Say "Hey Nexi, what's the weather in London?"
2. Expected: Weather response (may need API key for weather tool)
3. Alternative: "Hey Nexi, what's the capital of France?"
4. Expected: Direct answer via Gemini
5. If answer ends with "?", system should auto-followup

### Scenario 5: Multi-step (Agency)
1. Enable agency: `NEXI_AGENCY_AUTONOMY=true`
2. Say "Hey Nexi, research the best Python IDE"
3. Expected: Agency workflow executes (planner→research→tool→verify→reflect→report)
4. System should report findings via TTS

### Scenario 6: High-risk Action + Approval
1. Say "Hey Nexi, run script test.py"
2. Expected: 
   - If approval required: UI shows pending approval, system waits
   - If voice confirm enabled: system asks "Are you sure?"
3. Say "yes" or click approve

### Scenario 7: Consecutive Commands (Auto-Followup)
1. Set `NEXI_AUTO_FOLLOWUP_AFTER_TTS=true`
2. Say "Hey Nexi, search for AI news"
3. After TTS completes:
   - Expected: System stays awake (sleeping → online) instead of sleeping
   - Say "How about machine learning?"
4. Expected: System processes follow-up search

### Scenario 8: Interruption (Barge-in)
1. Say "Hey Nexi, tell me about artificial intelligence"
2. During TTS, say "Stop"
3. Expected: TTS stops immediately
4. System returns to sleep state

### Scenario 9: Error Recovery
1. Intentionally give an incomplete command: "Hey Nexi, email"
2. Expected: Clarification "Who should I email?"
3. Say "never mind"
4. Expected: System cancels and sleeps

### Scenario 10: No-Speech Timeout
1. Say "Hey Nexi" (wakes system)
2. Stay silent
3. Expected: System times out after 15 seconds of silence
4. System returns to sleep state

## Edge Cases

### Flash Attacks / Rapid Commands
1. Say "Hey Nexi" immediately after previous TTS completes
2. Expected: Session should handle normally (session lock prevents overlap)

### Gibberish Input
1. Say "asdfhjkasdf" during listening
2. Expected: Low confidence → clarification or "I didn't understand"

### Ambient Noise
1. Start system in moderately noisy environment
2. Say "Hey Nexi"
3. Expected: Wake detection should trigger (VAD thresholds may need tuning)

### Multiple Wake Words
1. Say "Hey Nexi" then immediately "Hey Jarvis"
2. Expected: First wake wins, second is ignored (session lock)

## Validation Conditions for PASS

- [ ] Full wake→command→TTS→sleep cycle completes in <10 seconds
- [ ] Clarification correctly detects missing slots and asks follow-up
- [ ] Auto-followup activates after questions
- [ ] Brain Q&A returns reasonable responses
- [ ] High-risk actions require approval
- [ ] Interruption stops TTS immediately
- [ ] No-speech timeout works
- [ ] Session lock prevents overlapping sessions
