# Safety & Verifier Report — Verified

## Approval Queue

File: `engine/approval_queue.py`

```python
class ApprovalQueue:
    def __init__(self, min_risk="high"):
        self.min_risk = min_risk
```

- `MIN_RISK` = "high" by default
- Tools with `safety >= "high"` require approval
- No timeout mechanism — blocks indefinitely if user doesn't respond

### High/Critical Risk Tools

| Tool | Risk | Requires Confirmation | Handler |
|------|------|----------------------|---------|
| clipboard_write_safe | high | yes | pyperclip.write |
| hand_gesture_control | high | yes | camera_control |
| eye_mouse_control | high | yes | camera_control |
| gesture_click_mode | high | yes | camera_control |
| click_ui_element | high | no | computer_use |
| type_text | high | no | computer_use |
| browser_click | high | no | browser_intelligence |
| browser_fill | high | no | browser_intelligence |
| forget_memory | medium | yes | memory_store |

## Safety Gate

File: `engine/safety_gate.py`

- `execution_is_safe(name, params)` — Checks:
  1. Is the tool blocked?
  2. Does the param contain dangerous patterns?
- Returns `{"allowed": bool, "reason": str, "requires_confirmation": bool}`

## Tool Result Verifier

File: `engine/tool_result_verifier.py`

- **Path verification only** — `path.exists()` for `create_file, create_folder, save_latest_output, create_file_from_latest_output`
- **Explicit flag** — Other tools rely on handler returning `verified: True`
- **No verification for**: screen_read, computer_use actions, browser actions, web searches, app opens, settings changes

## Bypass Analysis

| Path | Safety Gate | Approval Queue | Verifier |
|------|------------|----------------|----------|
| open_app | ❌ (risk=low) | ❌ | ❌ (no verify) |
| open_website | ❌ (risk=low) | ❌ | ❌ (no verify) |
| web_search | ❌ (risk=low) | ❌ | ❌ (no verify) |
| create_folder | ❌ (risk=medium) | ❌ | ✅ path exists |
| computer_use.click | ✅ | ✅ | ❌ no verify |
| computer_use.type_text | ✅ | ✅ | ❌ no verify |
| browser click/fill | ✅ | ✅ | ❌ no verify |
| Gemini brain output | ❌ | ❌ | ❌ no filter |

## Defects

1. **No approval timeout** — pending approvals block indefinitely
2. **Brain output bypasses ALL safety** — route="brain" goes directly to TTS
3. **Medium-risk tools have no approval** — create_folder, open_website skip approval
4. **Verifier is path-only** — no semantic verification for open_app, web_search, browser actions
5. **No voice prompt for approval** — pending approvals only visible in UI
