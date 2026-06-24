from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    critical: bool = True


CheckFn = Callable[[], CheckResult]


def _pass(name: str, detail: str = "", *, critical: bool = True) -> CheckResult:
    return CheckResult(name=name, status="PASS", detail=detail, critical=critical)


def _warn(name: str, detail: str = "", *, critical: bool = False) -> CheckResult:
    return CheckResult(name=name, status="WARN", detail=detail, critical=critical)


def _fail(name: str, detail: str = "", *, critical: bool = True) -> CheckResult:
    return CheckResult(name=name, status="FAIL", detail=detail, critical=critical)


def check_presence_state() -> CheckResult:
    from engine.presence_state import get_presence, reset_presence_state

    reset_presence_state()
    presence = get_presence()
    presence.update_mode("listening", attention="user", current_goal="demo preflight")
    data = presence.to_dict()
    if data["mode"] != "listening" or data["attention"] != "user":
        return _fail("PRESENCE", "presence state did not update")
    return _pass("PRESENCE", "state engine updates mode and attention")


def check_barge_in() -> CheckResult:
    from engine.barge_in_manager import get_barge_in_manager, reset_barge_in_state
    from engine.interrupt_controller import clear_interrupt, set_speaking
    from engine.turn_manager import clear_interrupt as clear_turn_interrupt

    reset_barge_in_state()
    clear_interrupt()
    clear_turn_interrupt()
    set_speaking(True)
    try:
        result = get_barge_in_manager().interrupt(source="demo_check", reason="preflight", speech_ms=2000)
        if not result.interrupted:
            return _fail("BARGE_IN", f"interrupt rejected: {result.reason}")
        return _pass("BARGE_IN", f"interrupt accepted level={result.level}")
    finally:
        set_speaking(False)
        clear_interrupt()
        clear_turn_interrupt()


def check_diagnostics() -> CheckResult:
    from engine.diagnostics import Diagnostics

    health = Diagnostics.check_all(force=True)
    failed = [name for name, status in health.items() if status.status == "error"]
    if failed:
        return _warn("DIAGNOSTICS", "error components: " + ",".join(failed))
    return _pass("DIAGNOSTICS", f"{len(health)} component checks returned")


def check_runtime_bridge() -> CheckResult:
    from engine.runtime_bridge import EVENT_INTERRUPTED, STATUS_TO_UI_STATE

    if STATUS_TO_UI_STATE.get(EVENT_INTERRUPTED) != "listening":
        return _fail("RUNTIME_BRIDGE", "interrupted status does not map to listening")
    return _pass("RUNTIME_BRIDGE", "interrupted status maps to listening")


def check_router() -> CheckResult:
    previous = os.environ.get("GROQ_INTENT_V2_ENABLED")
    os.environ["GROQ_INTENT_V2_ENABLED"] = "false"
    try:
        from engine.groq_intent_router_v2 import route_intent_v2

        result = route_intent_v2("open chrome", source="demo_check", context={})
        if result.get("route") not in {"tool", "clarify"}:
            return _fail("ROUTER", f"unexpected route={result.get('route')}")
        return _pass("ROUTER", f"route={result.get('route')} intent={result.get('intent')}")
    finally:
        if previous is None:
            os.environ.pop("GROQ_INTENT_V2_ENABLED", None)
        else:
            os.environ["GROQ_INTENT_V2_ENABLED"] = previous


def check_tts() -> CheckResult:
    from engine.diagnostics import Diagnostics

    result = Diagnostics.check_tts()
    if result.status == "error":
        return _warn("TTS", result.detail)
    return _pass("TTS", f"{result.status}: {result.detail}")


def check_tools() -> CheckResult:
    from engine.tool_registry import registered_tool_names

    names = registered_tool_names()
    if not names:
        return _fail("TOOLS", "no tools registered")
    return _pass("TOOLS", f"{len(names)} tools registered")


def check_session_sleep() -> CheckResult:
    from engine.wake_session_manager import are_detectors_paused, finish_session, start_session

    start_session("demo_check")
    finish_session("demo_check")
    if are_detectors_paused():
        return _fail("SESSION", "detectors still paused after finish_session")
    return _pass("SESSION", "finish_session resumes detectors")


CHECKS: list[CheckFn] = [
    check_presence_state,
    check_barge_in,
    check_diagnostics,
    check_runtime_bridge,
    check_router,
    check_tts,
    check_tools,
    check_session_sleep,
]


def run_checks(*, strict: bool = False) -> dict:
    results: list[CheckResult] = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(_fail(fn.__name__.replace("check_", "").upper(), type(exc).__name__))

    failed = [r for r in results if r.status == "FAIL" and (strict or r.critical)]
    warnings = [r for r in results if r.status == "WARN"]
    passed = [r for r in results if r.status == "PASS"]
    return {
        "passed": len(passed),
        "warnings": len(warnings),
        "failed": len(failed),
        "strict": strict,
        "results": [asdict(r) for r in results],
    }


def print_report(summary: dict) -> None:
    print("=" * 60)
    print("JARVIS PHASE 4 DEMO CHECK")
    print("=" * 60)
    for result in summary["results"]:
        status = result["status"]
        name = result["name"]
        detail = result.get("detail") or ""
        print(f"[{status}] {name}: {detail}")
    print("=" * 60)
    print(f"Result: {summary['passed']} PASS, {summary['warnings']} WARN, {summary['failed']} FAIL")
    if summary["failed"]:
        print("NOT DEMO READY")
    else:
        print("DEMO CHECK PASSED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis Phase 4 demo preflight check")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as blocking failures")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args(argv)

    summary = run_checks(strict=args.strict)
    if args.strict and summary["warnings"]:
        summary["failed"] += summary["warnings"]
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_report(summary)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
