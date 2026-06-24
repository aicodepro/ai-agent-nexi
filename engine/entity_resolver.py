from __future__ import annotations

from pathlib import Path


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().rstrip(".?!").split())


def resolve_user_path(value: str) -> dict[str, str | bool]:
    label = _norm(value)
    home = Path.home()
    aliases = {
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "documents": home / "Documents",
        "document": home / "Documents",
    }
    path = aliases.get(label)
    return {"matched": path is not None, "input": str(value or "").strip(), "path": str(path) if path else ""}


def resolve_entity(value: str, slot_type: str = "") -> dict:
    slot = _norm(slot_type)
    if slot in {"app", "app_name", "application"}:
        from engine.app_resolver import resolve_app_name

        return {"type": "app", **resolve_app_name(value)}
    if slot in {"url", "site", "website"}:
        from engine.website_resolver import resolve_website

        return {"type": "website", **resolve_website(value)}
    if slot in {"path", "folder", "location", "folder_location"}:
        return {"type": "path", **resolve_user_path(value)}

    from engine.website_resolver import looks_like_website, resolve_website

    if looks_like_website(value):
        return {"type": "website", **resolve_website(value)}
    from engine.app_resolver import resolve_app_name

    app = resolve_app_name(value)
    if app.get("matched"):
        return {"type": "app", **app}
    location = resolve_user_path(value)
    if location.get("matched"):
        return {"type": "path", **location}
    return {"type": "text", "matched": False, "input": str(value or "").strip(), "value": str(value or "").strip()}


def normalize_location_slots(slots: dict | None) -> dict:
    values = dict(slots or {})
    location = values.get("location") or values.get("folder_location") or values.get("path")
    if location and not values.get("location_path"):
        resolved = resolve_user_path(str(location))
        if resolved.get("matched"):
            values["location_path"] = resolved.get("path", "")
    return values
