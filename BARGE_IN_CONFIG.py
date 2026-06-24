def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}

# Raw config function to minimize risk of overwriting existing user settings
_env_bool("BARGE_IN_ENABLED", True)
