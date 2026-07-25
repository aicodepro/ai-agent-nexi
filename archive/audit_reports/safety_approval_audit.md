# Safety & Approval Audit

## Approval Queue — `engine/approval_queue.py`

### Architecture
```python
class ApprovalQueue:
    def __init__(self, min_risk="high"):
        self.min_risk = min_risk
        self.pending = Queue()
```

- `MIN_RISK` = "high" by default
- Tools with risk_level >= "high" require approval
- `add_request(tool_name, params, risk_level, ...)` — queues for approval
- `approve_next()` — approve top request
- `reject_next()` — reject top request
- `get_pending_summary()` — UI display

### Risk Levels (from tool_registry.py ToolSpec.safety)
- `low` — No approval needed (weather, search, open_app)
- `medium` — Possible approval (open_website, create_folder)
- `high` — Always requires approval (run_script, computer_use actions)
- `critical` — Always requires approval, no auto-approve

### Risk Examples by Tool
| Tool | Risk Level | Requires Confirmation | Approval Needed |
|------|-----------|----------------------|-----------------|
| open_app | low | false | No |
| open_website | medium | false | Only if min_risk=medium |
| web_search | low | false | No |
| create_folder | low | false | No |
| run_script | critical | true | Always |
| computer_use.screen_read | high | false | Always |
| computer_use.click | critical | true | Always |
| computer_use.type | high | true | Always |

## Safety Gate — `engine/safety_gate.py`

```python
def check_safety(tool_name, params):
    """Check if a tool action is safe to execute."""
    # Check for blocked tools
    # Check param safety
    # Return (safe, reason)
```

## Emergency Stop — `engine/control/safety.py`

- `EmergencyStop` — Global interrupt mechanism
- Called from `allCommands()` line 1774 with "stop" / "emergency stop"
- Sets event that triggers shutdown of dangerous operations

## Tool Proxy Safety — `engine/agency/nexi_tool_proxy.py`

- Proxy wraps tool execution with `check_safety()` call
- Verifies tool existence in registry
- Checks approval queue for high-risk tools
- Returns execution result or safety block message

## Post-Speak Safety — `tts_response_manager.py`

- `summarize_response_for_tts(text)` — truncates/summarizes long responses
- `get_post_speak_reply(response)` — generates one-liner follow-up

## Critical Findings

1. **`tool_result_verifier.py` is minimal** — Only checks `path.exists()` for create_file/create_folder. No verification of:
   - Web page loaded successfully
   - Search returned correct results
   - File has correct content
   - System state changed as expected

2. **No output guardrails on brain responses** — When route="brain", the Gemini response goes directly to TTS without safety checking. If Gemini hallucinates or returns malicious content, it's spoken aloud.

3. **No human-in-the-loop timeout** — If a high-risk action is queued for approval but the user doesn't respond, there's no timeout mechanism. The system blocks indefinitely.

4. **ApprovalQueue only surfaces via UI** — There's no voice prompt for pending approvals. The user must see the UI notification and click accept/reject. On audio-only mode, high-risk actions stall silently.

5. **No deny list for tools** — All registered tools are executable. There's no mechanism to dynamically block specific tools or commands based on context.

6. **Safety gate is basic** — `check_safety()` in `safety_gate.py` does not check for:
   - Command injection patterns
   - Path traversal in file operations
   - Rate limiting on dangerous operations
   - Context-appropriate restrictions (e.g., don't open browser during meeting)
