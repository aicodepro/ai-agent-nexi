# Feature Manifest & Slot Validation Audit

## Tool Registry — `engine/tool_registry.py`

All features are registered in `_TOOLS` (line 48-159) as `ToolSpec` with:
- `required_slots` — Defined for each tool
- `optional_slots` — Defined for each tool
- `safety` — risk level
- `requires_confirmation` — bool for high-risk actions
- `handler` — module path to handler function
- `aliases` — alternative phrasing
- `examples` — example queries

### Slot Validation

`execute_tool()` at line 309:
1. Checks `missing_slots()` at line 220 — returns slots missing from provided values
2. If missing, returns `{"expects_user_reply": True, "message": clarification_for_missing_slot(name, slot)}`
3. `clarification_for_missing_slot()` at line 228 generates human-readable questions like "Which app should I open?"

### Feature Manifest for Router

`router_tool_manifest()` at line 174 generates compact JSON cards with:
- name, description, aliases, examples, required_slots, optional_slots, risk_level, requires_confirmation, category

This is passed to the LLM router via `router_capability_manifest()` in `tool_manifest_loader.py`.

### Audit of Key Features

| Feature | required_slots | optional_slots | Has clarification | Follow-up |
|---------|---------------|----------------|-------------------|-----------|
| open_app | app_name | — | "Which app should I open?" | ✅ _handle_product_intelligence_v2 clarify handler |
| open_website | url | — | "Which website should I open?" | ✅ |
| web_search | query | — | "What should I search for?" | ✅ |
| create_folder | folder_name | — | "What should I name the folder?" | ✅ (via create_folder_workflow.py) |
| click_ui_element | — | target | None (optional slot) | ⚠️ No clarification if both missing |
| type_text | — | text | None (optional slot) | ⚠️ No clarification if both missing |
| weather_lookup | — | location | None | ⚠️ No mandatory slot |
| hand_gesture_control | mode | — | "Preview or control mode?" | ✅ |
| eye_mouse_control | mode | — | "Preview or control mode?" | ✅ |

### Problems

1. **Some tools have ONLY optional slots** (click_ui_element, type_text, weather_lookup) — If no slots are provided, `missing_slots()` returns empty and execution proceeds with empty values. These tools will likely fail silently.

2. **create_folder goes through TWO paths**: The router_v2 can route to `workflow->create_folder` (handled in `_handle_product_intelligence_v2()` line 917) which calls `start_create_folder()` for multi-turn dialogue. But `execute_tool()` in tool_registry also handles `create_folder` (line 416-423) with single-shot folder creation. This dual path can cause confusion.

3. **create_folder required_slots is ["folder_name"] but** the workflow also needs `location` — This is handled by the workflow, not the tool spec.

4. **Handler modules are late-imported strings** — No compile-time verification that handler functions exist.
