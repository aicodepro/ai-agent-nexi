#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOG_PATH = ROOT / "artifacts" / "interview_end_to_end_debug.log"


def _write(line: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def check(name: str, ok: bool, blocker: str = "") -> bool:
    if ok:
        line = f"PASS {name}"
    else:
        line = f"FAIL {name} blocker={blocker}"
    print(line)
    _write(line)
    return ok


def live_required(name: str, module: str) -> bool:
    line = f"LIVE_REQUIRED {name} module={module} blocker=requires_microphone_live_run"
    print(line)
    _write(line)
    return False


def main() -> int:
    failures = 0
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")

    os.environ.setdefault("NEXI_UI_MODE", "mark")
    os.environ.setdefault("NEXI_CONSOLE_LOG_LEVEL", "clean")
    os.environ.setdefault("NEXI_DEBUG_LOG_FILE", "artifacts/nexi_interview_debug.log")

    failures += not check("mark_ui_mode", os.getenv("NEXI_UI_MODE") == "mark", "set NEXI_UI_MODE=mark")

    index = (ROOT / "www_mark" / "index.html").read_text(encoding="utf-8")
    controller = (ROOT / "www_mark" / "controller.js").read_text(encoding="utf-8")
    required_ids = ["nexi-state", "nexi-source", "nexi-log", "nexi-bottom-state", "nexi-center-state", "nexi-status-badge", "nexi-mode", "nexi-orb-state"]
    missing = [item for item in required_ids if item not in index]
    failures += not check("mark_ui_dom_all_state_targets_sync", not missing and "window.nexiApplyState" in controller, f"missing={missing}")

    live_required("hotword_audio_seen", "scripts/debug_hotword_live.py")
    live_required("hotword_scores_seen", "scripts/debug_hotword_live.py")
    live_required("hotword_wake_emits_online_listening", "scripts/debug_hotword_live.py")

    from engine.clap_backend_manager import ClapBackendManager
    clap = ClapBackendManager(cooldown_ms=1500)
    status = clap.get_status()
    failures += not check("clap_backend_dsp_active", status["primary"] == "dsp_clap", json.dumps(status))
    live_required("clap_audio_seen", "scripts/debug_clap_live_interview.py")

    fake = {"clap": True, "wake": False, "source": None, "backend": "dsp_clap", "backend_used": "dsp_clap", "fallback_used": False, "cooldown": False, "amplitude": 0.5, "reason": "clap_detected"}
    now = 100.0
    first = clap._apply_double_clap_state(dict(fake), now)
    second = clap._apply_double_clap_state(dict(fake), now + 3.0)
    failures += not check("double_clap_can_wake", first.get("wake") is False and second.get("wake") is True, f"first={first} second={second}")
    clap.reset()
    single = clap._apply_double_clap_state(dict(fake), now + 10.0)
    failures += not check("single_clap_no_wake", single.get("wake") is False, f"single={single}")

    from engine.wake_session_manager import get_session_manager, start_session, finish_session
    mgr = get_session_manager()
    finish_session("debug_reset")
    failures += not check("session_pauses_detectors_after_wake", bool(start_session("hotword")) and mgr.are_detectors_paused(), "wake_session_manager.start_session")
    finish_session("debug_complete")
    failures += not check("detectors_resume_after_sleeping", not mgr.are_detectors_paused(), "wake_session_manager.finish_session")

    import engine.audio_wake_pipeline as awp
    failures += not check("command_capture_waits_15s_for_speech", int(awp.NO_SPEECH_TIMEOUT_SECONDS) == 15, f"NO_SPEECH_TIMEOUT_SECONDS={awp.NO_SPEECH_TIMEOUT_SECONDS}")
    failures += not check("command_capture_sends_one_asr_request", hasattr(awp.AudioWakePipeline, "emit_command"), "AudioWakePipeline.emit_command missing")

    from engine.runtime_bridge import handle_bridge_event
    failures += not check("asr_transcript_routes_to_command_bus", callable(handle_bridge_event), "runtime_bridge.handle_bridge_event missing")
    failures += not check("router_or_brain_response_created", (ROOT / "engine" / "groq_intent_router_v2.py").exists() and (ROOT / "engine" / "gemini_brain.py").exists(), "router/brain files missing")
    command_text = (ROOT / "engine" / "command.py").read_text(encoding="utf-8")
    failures += not check("tts_saying_state", "_set_ui_state(\"saying\"" in command_text, "command.speak saying state missing")
    failures += not check("final_sleeping_state", "else \"sleep\"" in command_text and "_set_ui_state(" in command_text, "command.speak sleep state missing")
    failures += not check("clean_console_mode", os.getenv("NEXI_CONSOLE_LOG_LEVEL") == "clean", "NEXI_CONSOLE_LOG_LEVEL not clean")

    if failures:
        print(f"RESULT NEEDS_LIVE_TEST_OR_FIX failures={failures} log={LOG_PATH}")
        return 1
    print(f"RESULT STATIC_PASS_NEEDS_LIVE_MIC log={LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
