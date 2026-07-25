# Brain Path Audit (How Questions Reach the LLM)

## Flow Overview

```
allCommands(text)
  ├── Pre-routing checks (emergency, stop, wake/sleep, etc.)
  ├── _handle_product_intelligence_v2(text)
  │   ├── route_intent_v2(text)
  │   │   ├── _deterministic_router(text)
  │   │   ├── _route_with_llm(text, manifest)
  │   │   └── return {route, intent, confidence, slots, ...}
  │   │
  │   ├── route == "brain" → _handle_brain_route(text, result)
  │   │   └── _respond_to_user(response, reason="brain")
  │   │       └── speak(response)
  │   │
  │   └── route == "tool" → execute_tool(intent, slots)
  │       └── result["message"] → speak()
  │
  ├── route_intent(text) [legacy fallback]
  │   └── route == "brain" → chatBot(text)
  │       └── speak(response)
  │
  └── dispatch_intent(result) [final fallback]
      └── brain/intent → chatBot(text)
```

## brain() function in intents.py

File: `engine/intents.py:83-105`

```python
def brain(query, *args, **kwargs):
    '''Uses smart brain to respond to ambiguous text.'''
    try:
        response = features.chatBot(query, disable_special_commands=True, ...)
        return {"action": "tell", "message": str(response), ...}
    except Exception as e:
        return {"action": "tell", "message": f"Error: {e}"}
```

## features.chatBot() — engine/features.py:598-619

```python
def chatBot(query, ...):
    '''Send query to the configured brain provider.'''
    provider = _get_provider()  # Gemini by default
    response = provider.generate_response(query, ...)
    return response
```

Provider chain:
1. Gemini (via `GEMINI_API_KEY` or `GOOGLE_API_KEY`) — default
2. HugChat (legacy, needs `JARVIS_ENABLE_LEGACY_BRAIN_PROVIDERS=true`)
3. Lightning AI (legacy, same gate)

## gemini_brain.py — engine/gemini_brain.py

```python
class GeminiBrain:
    def __init__(self, api_key=None, model="gemini-2.0-flash-exp", ...):
        self.model = genai.GenerativeModel(model)
    
    def generate_response(self, query, context=None, system_prompt=None):
        response = self.model.generate_content(prompt)
        return response.text
```

## Provider Registry — engine/providers/provider_registry.py

Has separate defaults for DeepSeek, GLM, Qwen, Kimi, MiniMax but NOT auto-wired into `features.chatBot()` startup. Requires `config/providers.local.json` manual config.

## Post-Brain Flow

```
chatBot() returns text
  → allCommands() line 1928-1930: return {"action": "tell", "message": str(response)}
  → caller dispatches to speak(response)
  → speak() at line 277:
      ├── _mark_question_response(response)
      │   ├── response_asks_question() → checks for "?" or question words
      │   └── if True: set pending followup, mark waiting for user
      ├── tts_provider_manager.speak(text)
      └── _set_ui_state("sleep" or "listening" based on expects_followup)
```

## Critical Findings

### 1. NO Post-Brain Classifier
All brain output goes straight to TTS. There is no:
- Safety filter on brain output
- Classification into: final_answer / needs_user_input / suggests_feature / unsafe / uncertain
- Fallback if brain returns error or empty
- If Gemini hallucinates an action (e.g., "I'll create a folder for you"), there's no mechanism to detect this and intercept it

### 2. Provider is Hard-coded to Gemini
Only Gemini is auto-configured. The other providers in `provider_registry.py` are not connected to the main flow. Even though the env file supports `DEEPSEEK_API_KEY`, `QWEN_API_KEY`, etc., these are not used by `features.chatBot()`.

### 3. No System Prompt for Router Mode
When route="brain", the response from Gemini is generated WITHOUT a structured output schema. If the LLM router (`_route_with_llm()`) fails, Gemini handles the query with only a basic system prompt (from `prompt_loader.py`), not a router-specific prompt.

### 4. No Tool-Aware Brain
When the brain is consulted, it doesn't know about available tools. If the user asks "browse to example.com", the brain might respond with "I can help with that" instead of actually using the browser_intelligence tool.

### 5. Error Handling Minima
`brain()` function in intents.py has only `try/except Exception as e: return error message`. No retry, no fallback, no graceful degradation.
