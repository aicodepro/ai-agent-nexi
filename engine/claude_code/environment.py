"""Minimal subprocess environments for Claude Code and generated test runs."""

from __future__ import annotations

import os


_BASE_KEYS = {
    "APPDATA",
    "COMSPEC",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}
_CLAUDE_KEYS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CONFIG_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
}


def sanitized_environment(*, for_claude: bool = False) -> dict[str, str]:
    allowed = _BASE_KEYS | (_CLAUDE_KEYS if for_claude else set())
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment["NEXI_STUDIO_CHILD"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment
