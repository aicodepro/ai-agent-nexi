"""Offline Nexi Access contract harness.

This harness validates deterministic contracts without pretending to validate a
physical microphone, screen reader, Spotify account, or external provider quota.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _check(name, callback) -> dict:
    started = time.perf_counter()
    try:
        detail = callback()
        return {
            "name": name,
            "status": "pass",
            "detail": str(detail or "contract satisfied"),
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "fail",
            "detail": f"{type(exc).__name__}: {exc}",
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }


def _router_contract():
    from engine.router_v3 import route_intent_v3

    play = route_intent_v3("play the album Discovery on Spotify", source="acceptance")
    assert play["intent"] == "spotify_play" and play["slots"]["kind"] == "album"
    search = route_intent_v3("search latest Python security news", source="acceptance")
    assert search["intent"] == "web_search"
    return "Router V3 selected Spotify and live-search tools deterministically"


def _response_contract():
    from engine.response_coordinator import ResponseCoordinator

    coordinator = ResponseCoordinator()
    assert coordinator.accept("First", request_id="one", session_id="s", session_epoch=2).accepted
    assert not coordinator.accept("Duplicate", request_id="one", session_id="s", session_epoch=2).accepted
    assert not coordinator.accept("Stale", request_id="old", session_id="s", session_epoch=1).accepted
    return "duplicate and stale responses rejected"


def _transcript_contract():
    from engine.transcript_filter import assess_transcript

    assert assess_transcript("next").accepted
    assert not assess_transcript("um").accepted
    assert assess_transcript("chrome", pending_followup=True).accepted
    return "short commands/follow-ups accepted; filler rejected"


def _accessibility_contract():
    from engine.accessibility_feedback import earcon_for_state
    from engine.ui_state_manager import UIStateManager

    manager = UIStateManager(dedupe_ms=0)
    manager._post_to_eel = lambda _event: True
    states = ["online", "listening", "recognising", "thinking", "saying", "sleep"]
    events = [manager.emit(state, session_id="access", session_epoch=1) for state in states]
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert all(earcon_for_state(state) for state in states)
    return "ordered status events expose non-visual earcon cues"


def _temporal_contract():
    from engine.memory.temporal_memory import TemporalMemory

    with tempfile.TemporaryDirectory() as folder:
        memory = TemporalMemory(Path(folder) / "temporal.json")
        fact = memory.store(
            "current fact",
            "Cited current value",
            source="acceptance",
            ttl_seconds=60,
            citations=[{"url": "https://example.test"}],
        )
        assert fact is not None and not fact.stale
        recalled = memory.recall("current fact")
        assert recalled is not None and recalled.retrieval_behavior == "live_first_explicit_stale_only"
    return "temporal fact persisted with source and expiry"


def _spotify_contract():
    from engine.integrations.spotify import REDIRECT_URI, MemoryTokenStore, SpotifyOAuth

    url, verifier, state = SpotifyOAuth("acceptance-client", token_store=MemoryTokenStore()).authorization_url()
    params = parse_qs(urlparse(url).query)
    assert params["redirect_uri"] == [REDIRECT_URI]
    assert params["code_challenge_method"] == ["S256"]
    assert verifier and state
    return "PKCE URL uses exact loopback callback and state"


def run_contract_harness() -> dict:
    checks = [
        _check("router_v3", _router_contract),
        _check("response_coordinator", _response_contract),
        _check("transcript_quality", _transcript_contract),
        _check("accessibility_status", _accessibility_contract),
        _check("temporal_memory", _temporal_contract),
        _check("spotify_pkce", _spotify_contract),
    ]
    return {
        "schema_version": 1,
        "generated_at": time.time(),
        "contract_pass": all(item["status"] == "pass" for item in checks),
        "checks": checks,
        "external_validation_required": [
            "physical microphone and false-wake soak",
            "blind screen-reader walkthrough",
            "Spotify account authorization and Premium playback",
            "restart persistence through Windows Credential Manager",
        ],
    }


def main() -> int:
    report = run_contract_harness()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
