"""Minimal child-process environments for supported agent runtimes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from engine.claude_code.environment import sanitized_environment


_PROXY_KEYS = {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}
_PROVIDER_KEYS = {
    "opencode": {
        "OPENCODE_GIT_BASH_PATH",
        "OPENCODE_SERVER_PASSWORD",
    },
    "hermes": {
        "HERMES_HOME",
        "HERMES_PROFILE",
    },
    "openclaw": {
        "OPENCLAW_HOME",
        "OPENCLAW_GATEWAY_URL",
        "OPENCLAW_GATEWAY_TOKEN",
    },
    "antigravity": {
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    },
}


def runtime_environment(provider_id: str, control_cwd: str | None = None) -> dict[str, str]:
    environment = sanitized_environment(for_claude=False)
    allowed = _PROXY_KEYS | _PROVIDER_KEYS.get(provider_id, set())
    configured = str(os.getenv("NEXI_AGENT_RUNTIME_ENV_ALLOWLIST") or "")
    allowed.update(item.strip().upper() for item in configured.split(",") if item.strip())
    for key, value in os.environ.items():
        if key.upper() in allowed:
            environment[key] = value
    if provider_id == "opencode" and control_cwd:
        root = Path(control_cwd).resolve()
        config_dir = root / "opencode-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        isolated_home = root / "opencode-home"
        xdg_config = root / "xdg-config"
        xdg_data = isolated_home / ".local" / "share"
        appdata = root / "appdata"
        localappdata = root / "localappdata"
        programdata = root / "programdata"
        for directory in (isolated_home, xdg_config, xdg_data, appdata, localappdata, programdata):
            directory.mkdir(parents=True, exist_ok=True)
        xdg_config.mkdir(parents=True, exist_ok=True)
        environment["OPENCODE_CONFIG_DIR"] = str(config_dir.resolve())
        environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
        environment["OPENCODE_DISABLE_DEFAULT_PLUGINS"] = "1"
        environment["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"
        environment["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
        environment["OPENCODE_PURE"] = "1"
        environment["HOME"] = str(isolated_home)
        environment["USERPROFILE"] = str(isolated_home)
        environment["XDG_CONFIG_HOME"] = str(xdg_config.resolve())
        environment["XDG_DATA_HOME"] = str(xdg_data.resolve())
        environment["APPDATA"] = str(appdata.resolve())
        environment["LOCALAPPDATA"] = str(localappdata.resolve())
        environment["PROGRAMDATA"] = str(programdata.resolve())
        source_home = Path(os.getenv("USERPROFILE") or os.getenv("HOME") or Path.home()).expanduser()
        source_auth = source_home / ".local" / "share" / "opencode" / "auth.json"
        target_auth = xdg_data / "opencode" / "auth.json"
        if source_auth.is_file():
            try:
                auth = json.loads(source_auth.read_text(encoding="utf-8"))
                if isinstance(auth, dict):
                    auth = {
                        key: value
                        for key, value in auth.items()
                        if not (isinstance(value, dict) and value.get("type") == "wellknown")
                    }
                    target_auth.parent.mkdir(parents=True, exist_ok=True)
                    target_auth.write_text(json.dumps(auth), encoding="utf-8")
                    target_auth.chmod(0o600)
            except (OSError, ValueError, TypeError):
                pass
    environment["NEXI_AGENT_RUNTIME_PROVIDER"] = provider_id
    return environment
