# Post-Brain Output Gap Report — Verified

## Current Flow

```
route_intent_v2("what is the capital of France")
  → _deterministic_router()
    → _qa_like("what is the capital of france") → True
    → route="brain", intent="general_qa", confidence=0.86
  → allCommands() → _handle_product_intelligence_v2()
    → route="brain"
      → _handle_brain_route(text, result)  [command.py:~900-970]
        → brain_response = chatBot(text) via features.py
          → ask_brain(query) → Gemini generates text
          → guard_unverified_action_message() ← pattern-text only
          → speak(response_text)
```

## What's Missing

There is **no structured output classification** between Gemini and TTS. The code path:

1. `features.chatBot()` line 598-619: Calls `ask_brain()`, runs `guard_unverified_action_message()` (text pattern matching), then `speak(response_text)`
2. `_mark_question_response()` in `speak()` (command.py:166-206): Uses `response_asks_question()` which checks:
   - Does text end with `?`
   - Does text start with question words?
   - Is it a rhetorical phrase?
3. `make_response()` in `assistant_response.py`: Returns `expects_user_reply: bool` and `followup_type: str`

## Missing Classifications

| Classification | Needed | Current |
|---------------|--------|---------|
| `final_answer` | Spoken, session ends | ✅ Spoken, but session end depends on env var |
| `needs_user_input` | Question detected, auto-follow-up | ✅ Via `response_asks_question()` — text-based only |
| `suggests_action` | Route back through safety/router | ❌ **MISSING** — Gemini can say "I'll create a folder" but no action routing |
| `unsafe_content` | Block TTS, log warning | ❌ **MISSING** — Gemini output goes to TTS unfiltered |
| `uncertain_response` | Clarify instead of speak | ❌ **MISSING** — "I'm not sure" spoken as fact |
| `errors` | Retry, fallback, graceful degrade | ❌ **MISSING** — Error message spoken directly |
| `feature_request` | Log and suggest approval | ❌ **MISSING** — User asks "Can you browse Twitter?" goes to Gemini, not feature_gap |

## Impact

Without a structured post-brain classifier, Gemini output is **uncontrolled**:
- If Gemini hallucinates an action ("I just opened Chrome"), the system doesn't catch it
- If Gemini returns unsafe content, it's spoken aloud
- If Gemini asks a question without `?`, follow-up isn't triggered
- If Gemini says "I don't know", there's no confidence check or fallback

## Desired Architecture

```
Gemini raw response
  → PostBrainClassifier.classify(response) → {
      type: "answer" | "action_suggestion" | "needs_input" | "unsafe" | "error",
      content: "...",
      suggested_action: {tool, slots} | null,
      risk: "low" | "medium" | "high",
      confidence: 0.0-1.0
    }
  → If action_suggestion → route through safety/approval
  → If unsafe → block, log, alternative response
  → If needs_input → speak + auto-follow-up
  → If answer → speak + session end
```
