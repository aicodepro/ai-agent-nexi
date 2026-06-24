from __future__ import annotations


APP_ALIASES = {
    "browser": "chrome",
    "internet": "chrome",
    "chrome": "chrome",
    "google chrome": "chrome",
    "code": "VS Code",
    "vscode": "VS Code",
    "vs code": "VS Code",
    "visual studio code": "VS Code",
    "notepad": "notepad",
    "calculator": "calculator",
    "calc": "calculator",
}


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().rstrip(".?!").split())


def resolve_app_name(value: str) -> dict[str, str | bool]:
    raw = str(value or "").strip()
    normalized = _norm(raw)
    app_name = APP_ALIASES.get(normalized, raw)
    return {"matched": normalized in APP_ALIASES, "input": raw, "app_name": app_name}


def normalize_app_slot(slots: dict | None) -> dict:
    values = dict(slots or {})
    app_name = values.get("app_name") or values.get("app") or values.get("application")
    if app_name:
        values["app_name"] = str(resolve_app_name(str(app_name)).get("app_name") or app_name).strip()
    return values
