# Identity & Response Style Audit

## System Identity

The system has TWO identities:

### 1. **Nexi** (Primary — used in code)
- `nexi_wake_controller.py` — "NexiWakeController"
- `engine/agency/__init__.py` — "Nexi Agency Engine"
- `engine/features.py` — `nexi_chat()` function (line 620)
- `engine/voice_state_machine.py` — All state IDs prefixed with "nexi_"
- `engine/command.py` — Pending follow-ups and workflow contexts

### 2. **Jarvis** (Legacy — used in codebase roots)
- `run.py` — `jarvis.db`, `start_jarvis()` (commented)
- `engine/features.py` — `JARVIS` class, `jarvis.db`
- Old test files reference Jarvis
- `.env.example` — `JARVIS_` env var names

### Identity in Responses

The system prompts (from `prompt_loader.py`) define:
- System name: Nexi
- Personality: "helpful, autonomous AI assistant"
- Response style: natural, conversational, proactive

## Response Style Problems

### 1. No Fallback Template
When the LLM router or brain fails, the fallback is:
```python
{"action": "tell", "message": "I'm sorry, I couldn't process that."}
```
(command.py line 1960 — this is generic and unhelpful)

### 2. No Response Length Control
- Gemini responds with free-form text
- `summarize_response_for_tts()` truncates but doesn't reformat
- No guaranteed response structure for voice (which needs short, concise answers)

### 3. No Proactive Response Template
- Agent has tools for proactive suggestion (`suggest_feature`, `ask_if_ready`)
- But these are only triggered by specific commands, not autonomously
- No "what should I do next?" baseline initiative

### 4. Response Sources
| Source | How | Quality |
|--------|-----|---------|
| Router `route="brain"` | Gemini raw text | Variable — no structure |
| Router `route="tool"` | Tool result message | Best — structured |
| Router `route="clarify"` | Clarification template | Good — predefined |
| Router `route="reject"` | "I can't help with that" | Generic |
| Legacy router `brain` | Gemini raw | Variable |
| `dispatch_intent()` | Gemini raw | Variable |
| Error fallback | "I'm sorry..." | Generic |
| Agency workflow report | Gemini-generated report | Structured |

### Key Issues

1. **Brain responses are uncontrolled** — Most Q&A goes through Gemini with no:
   - Length limit
   - Safety filter
   - Format template (should end with question? should suggest action?)
   - `source_of_truth` marker ("I believe" vs "I know")

2. **No distinction between LLM confidence levels** — "I don't know" vs "Here's a definitive answer" are spoken the same way.

3. **No multi-modal response** — All responses are text→TTS. There's no mechanism for:
   - Showing a chart/screenshot
   - Opening a document
   - Playing audio
   - Triggering a UI animation

4. **Tool success/failure is spoken as-is** — Tool result messages come from the handler. Some are terse ("Done."), some are verbose. No standardization.
