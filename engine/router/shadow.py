"""Shadow-mode observer (migration Phase B).

Runs the Master Router next to the live router on every real command and logs
where they agree/disagree — WITHOUT touching the live decision. This gathers
real-world evidence so the new router can be proven before it takes the wheel.

Safe by construction:
  * gated by env NEXI_ROUTER_SHADOW (default on; set 0/false/off to disable),
  * routes in a daemon thread → zero added latency on the live path,
  * never raises into the caller (all failures swallowed).

Inspect results:
    python -m engine.router.shadow            # agreement summary + sample disagreements
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

_LOG_PATH = os.path.join("data", "nexi", "router", "shadow.jsonl")
_WRITE_LOCK = threading.Lock()


def _enabled() -> bool:
    return (os.getenv("NEXI_ROUTER_SHADOW", "1") or "").strip().lower() not in {"0", "false", "no", "off"}


def observe(text: str, live_result: dict[str, Any], source: str = "") -> None:
    """Fire-and-forget: score the new router against the live decision. Never raises."""
    if not _enabled() or not (text or "").strip():
        return
    try:
        threading.Thread(
            target=_run, args=(text, dict(live_result or {}), source), daemon=True
        ).start()
    except Exception:
        pass


def _run(text: str, live_result: dict, source: str) -> None:
    try:
        from engine.router import get_router

        router = get_router()
        started = time.time()
        decision = router.route(text)
        elapsed_ms = round((time.time() - started) * 1000, 1)
        live_route = str(live_result.get("route") or "")
        live_intent = str(live_result.get("intent") or "")
        _append({
            "text": text[:200],
            "source": source,
            "live": {"route": live_route, "intent": live_intent},
            "shadow": {
                "route": decision.route, "intent": decision.intent, "band": decision.band,
                "sim": decision.sim, "margin": decision.margin,
            },
            "agree_route": live_route == decision.route,
            "agree_intent": live_intent == decision.intent,
            "embedder": getattr(router.semantic.emb, "name", "?"),
            "ms": elapsed_ms,
        })
    except Exception:
        pass  # shadow observation must never disturb the live path


def _append(rec: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with _WRITE_LOCK, open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def summarize(path: str = _LOG_PATH) -> dict:
    """Report route/intent agreement between the live and shadow routers."""
    total = agree_route = agree_intent = 0
    disagreements: list[dict] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                total += 1
                agree_route += int(rec.get("agree_route", False))
                agree_intent += int(rec.get("agree_intent", False))
                if not rec.get("agree_intent", False) and len(disagreements) < 25:
                    disagreements.append(rec)
    except FileNotFoundError:
        pass
    return {
        "n": total,
        "route_agreement": round(agree_route / total, 3) if total else 0.0,
        "intent_agreement": round(agree_intent / total, 3) if total else 0.0,
        "disagreements": disagreements,
    }


def _print_summary(path: str = _LOG_PATH) -> None:
    s = summarize(path)
    print(f"\n=== shadow log: {path} ===")
    print(f"observations    : {s['n']}")
    print(f"route agreement : {s['route_agreement']:.1%}")
    print(f"intent agreement: {s['intent_agreement']:.1%}")
    if s["disagreements"]:
        print("sample disagreements (live -> shadow):")
        for rec in s["disagreements"][:15]:
            live, shadow = rec["live"], rec["shadow"]
            print(f"  {rec['text'][:38]:38} {live['intent']:22} -> {shadow['intent']:22} ({shadow['band']})")


def _demo() -> None:
    import tempfile

    global _LOG_PATH
    original = _LOG_PATH
    _LOG_PATH = os.path.join(tempfile.mkdtemp(), "shadow.jsonl")
    try:
        # synchronous path so the test is deterministic (observe() is async)
        _run("what time is it", {"route": "tool", "intent": "tell_time"}, "test")
        _run("open notepad", {"route": "tool", "intent": "open_app"}, "test")
        s = summarize(_LOG_PATH)  # explicit: summarize()'s default path binds at import
        assert s["n"] == 2, s
        assert 0.0 <= s["route_agreement"] <= 1.0
        print(f"shadow._demo OK  (logged {s['n']}, route_agreement={s['route_agreement']:.0%})")
    finally:
        _LOG_PATH = original


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        _demo()
    else:
        _print_summary()
