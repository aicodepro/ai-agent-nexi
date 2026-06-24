from __future__ import annotations

from typing import Any

from engine.intent_taxonomy import OUTPUT_INTENTS, exact_schema


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_slots(intent: str, slots: dict | None, text: str = "") -> tuple[str, dict[str, Any]]:
    current_intent = str(intent or "unknown").strip()
    values: dict[str, Any] = {str(k): v for k, v in dict(slots or {}).items() if v is not None}

    if current_intent == "open_app":
        app_name = values.get("app_name") or values.get("app") or values.get("application") or values.get("target")
        if app_name:
            from engine.website_resolver import looks_like_website, resolve_website

            target = _clean_text(app_name)
            if looks_like_website(target):
                current_intent = "open_website"
                values = {"url": resolve_website(target).get("url", target)}
            else:
                from engine.app_resolver import resolve_app_name

                values["app_name"] = resolve_app_name(target).get("app_name", target)

    if current_intent == "open_website":
        from engine.website_resolver import normalize_website_slot

        values = normalize_website_slot(values)

    if current_intent == "web_search":
        query = values.get("query") or values.get("search_query") or values.get("text")
        if query:
            values["query"] = _clean_text(query)

    if current_intent in {"create_folder", "create_project_folder", "create_file"}:
        from engine.entity_resolver import normalize_location_slots

        values = normalize_location_slots(values)
        if values.get("folder_name"):
            values["folder_name"] = _clean_text(values["folder_name"])
        if values.get("file_name"):
            values["file_name"] = _clean_text(values["file_name"])

    if current_intent in OUTPUT_INTENTS and values.get("file_name"):
        values["file_name"] = _clean_text(values["file_name"])

    return current_intent, values


def normalize_router_result(result: dict, text: str = "") -> dict:
    normalized = exact_schema(result)
    intent, slots = normalize_slots(normalized.get("intent", ""), normalized.get("slots") or {}, text=text)
    normalized["intent"] = intent
    normalized["slots"] = slots
    if normalized["route"] == "tool" and intent in OUTPUT_INTENTS:
        normalized["route"] = "output"
        normalized["should_call_tool"] = False
    return exact_schema(normalized)
