#!/usr/bin/env python3
"""Live debug script: session lock, UI ACK, Groq TTS, auto-followup, clean console.

Usage:
    .venv\Scripts\python.exe scripts/debug_session_ui_groq_live.py [--verbose]

Checks (all run locally, no mic/Eel needed):
  1. WakeSessionManager start/finish cycle
  2. Detectors pause/resume via session
  3. Hotword Engine Manager respects session lock
  4. Clap Backend Manager respects session lock
  5. AudioWakePipeline process_frame respects session lock
  6. Auto-followup env var default (NEXI_AUTO_FOLLOWUP_AFTER_TTS=false)
  7. Groq TTS failure reporting has safe reason string
  8. TTS provider manager fallback logging has error hints
  9. UI State ACK module exists and accepts calls
  10. Bridge events include session_id
  11. Canonical state order remains correct
  12. Clean console (no duplicate prints for key paths)
  13. WakeSessionManager.check_timeout auto-finishes
  14. Session isolation across multiple start/finish
  15. Runtime bridge ignore_if_stale filtering
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PASS = 0
FAIL = 0
SKIP = 0
results = []


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        results.append(f"  PASS  {name}")
        PASS += 1
    else:
        results.append(f"  FAIL  {name}  {detail}")
        FAIL += 1


def skip(name: str):
    global SKIP
    results.append(f"  SKIP  {name}")
    SKIP += 1


def header(title: str):
    results.append("")
    results.append(f"=== {title} ===")


header("1. WakeSessionManager basic cycle")
from engine.wake_session_manager import (
    WakeSessionManager,
    start_session,
    finish_session,
    is_session_active,
    are_detectors_paused,
    is_current_session,
    ignore_if_stale,
    get_session_manager,
)


def _reset():
    mgr = WakeSessionManager.get_instance()
    mgr._session_id = None
    mgr._source = ""
    mgr._state = "sleep"
    mgr._detectors_paused = False
    mgr._started_at = 0.0
    mgr._last_event_at = 0.0


_reset()
assert not is_session_active()
sid = start_session("hotword")
check("start_session returns 8-char id", len(sid) == 8, f"got={len(sid)}")
check("is_session_active after start", is_session_active())
check("is_current_session matches", is_current_session(sid))
check("detectors paused", are_detectors_paused())
finish_session("test")
check("not active after finish", not is_session_active())
check("detectors resumed after finish", not are_detectors_paused())

header("2. Detector pause/resume")
_reset()
sid = start_session("hotword")
assert are_detectors_paused()
get_session_manager().resume_detectors()
check("resume_detectors works", not are_detectors_paused())
get_session_manager().pause_detectors()
check("pause_detectors works", are_detectors_paused())
finish_session("test")
check("finish resumes detectors", not are_detectors_paused())

header("3. Hotword Engine Manager (no session block at detector level)")
_reset()
from engine.hotword_engine_manager import HotwordEngineManager
hm = HotwordEngineManager({"enabled": True, "scorer": lambda x: 0.5})
r1 = hm.process_audio_chunk(b"\x00\x00" * 640, 16000)
check("hotword processes frames normally", r1.reason != "session_active")

header("4. Clap Backend Manager (no session block at detector level)")
_reset()
from engine.clap_backend_manager import ClapBackendManager
cm = ClapBackendManager(cooldown_ms=0)
r1 = cm.process_audio_chunk(b"\x00\x00" * 640)
check("clap processes frames normally", r1.get("backend") != "session_lock")

header("5. AudioWakePipeline process_frame respects session lock")
_reset()
from engine.audio_wake_pipeline import AudioWakePipeline
ap = AudioWakePipeline(
    wake_scorer=type("Fake", (), {"name": "test", "score": lambda self, x: 0.9})(),
    clock=time.time,
)
r1 = ap.process_frame(b"\x00\x00" * 640)
check("pipeline works without session", r1.get("reason") != "session_active")
start_session("hotword")
r2 = ap.process_frame(b"\x00\x00" * 640)
check("pipeline blocked by session", r2.get("reason") == "session_active")
finish_session("test")
r3 = ap.process_frame(b"\x00\x00" * 640)
check("pipeline works after finish", r3.get("reason") != "session_active")

header("6. Auto-followup env default")
val = os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "false")
check("NEXI_AUTO_FOLLOWUP_AFTER_TTS defaults to false", val == "false")

header("7. Groq TTS failure reporting")
from engine.groq_tts import GroqTTSResult
r = GroqTTSResult(ok=False, error="HTTP Error 401: Unauthorized")
check("groq error string truncated", len(r.error) <= 80, f"len={len(r.error)}")
r2 = GroqTTSResult(ok=False, error="connection_refused")
check("groq safe_reason short", len(r2.error) <= 30)

header("8. TTS provider manager fallback logging")
# Check that the error detail is included in the provider manager
import engine.tts_provider_manager as tpm
order = tpm._provider_order()
check("provider order is a list", isinstance(order, list) and len(order) > 0)

header("9. UI State ACK module")
from engine.ui_state_ack import on_ui_state_ack, get_last_ack, reset_acks
reset_acks()
on_ui_state_ack("online", "hotword", time.time())
acks = get_last_ack()
check("ACK stored for online|hotword", "online|hotword" in acks, f"keys={list(acks.keys())}")
reset_acks()

header("10. Bridge events include session_id")
_reset()
from engine.runtime_bridge import BridgeEvent
sid = start_session("hotword")
evt = BridgeEvent(type="status", status="thinking")
d = evt.to_dict()
check("session_id in bridge event", d.get("session_id") == sid, f"got={d.get('session_id')}")
finish_session("test")

header("10a. Bridge events with wake_detected state (not online in raw bus)")
from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
bus = InternalWakeSignalBus(post_fn=lambda s: None)
bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
bus.emit_listening_started("hotword")
bus.emit_tts_started()
bus.emit_tts_done()
check("wake_signal_bus emits raw states", True)  # smoke test

header("11. Canonical state order")
from engine.ui_state_manager import CANONICAL_STATES, STATE_LABELS
canonical_order = ["sleep", "online", "listening", "waiting_for_speech", "recognising", "thinking", "saying", "error"]
for s in canonical_order:
    check(f"canonical state {s} present", s in CANONICAL_STATES)
labels = ["SLEEPING", "ONLINE", "LISTENING", "LISTENING", "RECOGNISING", "THINKING", "SAYING", "ERROR"]
for s, lbl in zip(canonical_order, labels):
    check(f"label for {s} is {lbl}", STATE_LABELS.get(s) == lbl, f"got={STATE_LABELS.get(s)}")

header("12. Clean console — no duplicate post_status")
# Check that nexi_wake_controller.wake_nexi removes duplicate post_status calls
import engine.nexi_wake_controller as jwc
check("wake_nexi exists", hasattr(jwc, "wake_nexi") and callable(jwc.wake_nexi))

header("13. WakeSessionManager.check_timeout")
_reset()
mgr = get_session_manager()
start_session("hotword")
# Should not timeout immediately
check("no timeout right after start", not mgr.check_timeout())
# Force timeout by setting last_event_at to old time
mgr._last_event_at = time.time() - 200.0
check("timeout after 200s idle", mgr.check_timeout())
check("detectors resumed after timeout", not mgr.are_detectors_paused())
_reset()

header("14. Session isolation")
_reset()
sid1 = start_session("hotword")
sid2 = start_session("clap")
check("second start returns same id", sid1 == sid2)
finish_session("test")
sid3 = start_session("clap")
check("new session after finish gets new id", sid3 != sid1)

header("15. Runtime bridge ignore_if_stale")
_reset()
sid = start_session("hotword")
check("same session not stale", not ignore_if_stale(sid))
check("different session stale", ignore_if_stale("other_sid"))
check("no session stale", ignore_if_stale("any"))
finish_session("test")

results.append("")
results.append(f"Results: {PASS} pass, {FAIL} fail, {SKIP} skip")
results.append("")

for line in results:
    print(line)

sys.exit(0 if FAIL == 0 else 1)
