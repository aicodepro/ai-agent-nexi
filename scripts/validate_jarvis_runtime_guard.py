from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _ok(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"{status}: {label}{suffix}")
    return condition


def main() -> int:
    checks: list[bool] = []
    plugin_dir = ROOT / ".opencode" / "plugins" / "jarvis-runtime-guard"
    skill_file = ROOT / ".opencode" / "skills" / "jarvis-voice-bridge-runtime" / "SKILL.md"
    mcp_design = ROOT / "OPENCODE_JARVIS_RUNTIME_MCP_DESIGN.md"
    opencode_config = _read(ROOT / ".opencode" / "opencode.json")

    checks.append(_ok("runtime guard plugin folder exists", plugin_dir.is_dir()))
    checks.append(_ok("plugin README exists", (plugin_dir / "README.md").is_file()))
    checks.append(_ok("plugin design exists", (plugin_dir / "plugin-design.md").is_file()))
    checks.append(_ok("voice bridge skill exists", skill_file.is_file()))
    checks.append(_ok("MCP design exists", mcp_design.is_file()))
    checks.append(_ok("plugin is not auto-loaded", "jarvis-runtime-guard" not in opencode_config))

    wake_files = [
        ROOT / "engine" / "audio_wake_pipeline.py",
        ROOT / "engine" / "hotword_engine_manager.py",
        ROOT / "engine" / "jarvis_wake_controller.py",
    ]
    cloud_before_wake = False
    for path in wake_files:
        text = _read(path).lower()
        if path.name == "audio_wake_pipeline.py":
            # ASR after wake is allowed in this file; process_frame must stay cloud-free.
            section = text.split("def process_frame", 1)[-1].split("def _post_status", 1)[0]
        else:
            section = text
        if re.search(r"\b(groq|gemini|google_api_key|groq_api_key)\b", section):
            cloud_before_wake = True
    checks.append(_ok("no cloud provider in wake detection logic", not cloud_before_wake))

    mark_main = _read(ROOT / "www_mark" / "main.js")
    checks.append(_ok("Mark UI routes typed text through ui_submit_text", "eel.ui_submit_text" in mark_main))
    checks.append(_ok("Mark UI does not call eel.allCommands directly", "eel.allCommands" not in mark_main))

    controller = _read(ROOT / "www_mark" / "controller.js")
    for fn in ["updateJarvisState", "senderText", "receiverText", "appendLog", "DisplayMessage", "ShowHood"]:
        checks.append(_ok(f"eel.expose present for {fn}", f"'{fn}'" in controller or f'"{fn}"' in controller))

    forbidden_secret_patterns = ["sk-", "GROQ_API_KEY=", "GEMINI_API_KEY="]
    combined = "\n".join(_read(p) for p in [skill_file, plugin_dir / "README.md", plugin_dir / "plugin-design.md", mcp_design])
    checks.append(_ok("no obvious secrets in guard docs", not any(p in combined for p in forbidden_secret_patterns)))

    passed = sum(1 for check in checks if check)
    failed = len(checks) - passed
    print(f"RESULTS: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
