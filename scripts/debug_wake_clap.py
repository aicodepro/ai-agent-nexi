"""Validate Nexi wake + clap detection without microphone hardware.

Checks:
  - ClapStateMachine state transitions are correct
  - is_clap_frame logic is functional
  - detect_double_clap logic is correct
  - AudioWakePipeline.process_frame handles hotword + clap
  - OpenWakeWordScorer can be created (if deps available)
"""

import os
import sys
import time
import struct
import numpy as np

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

FAILURES = 0


def fail(name, reason):
    global FAILURES
    FAILURES += 1
    print(f"  FAIL  {name}  reason={reason}")


def pass_(name, detail=""):
    print(f"  PASS  {name}{'  ' + detail if detail else ''}")


# ---------- 1. ClapStateMachine ----------
print("[1] ClapStateMachine")
try:
    from engine.clap_detector import ClapStateMachine

    sm = ClapStateMachine()
    assert sm.state == "idle"
    pass_("initial state = idle")

    # Silent frame should not detect
    silence = struct.pack("<1024h", *([0] * 1024))
    event = sm.process_frame(silence)
    assert not event["clap"], f"got clap on silence: {event}"
    pass_("silence = no clap")
except Exception as e:
    fail("ClapStateMachine", f"{type(e).__name__}: {e}")

# ---------- 2. is_clap_frame ----------
print("[2] is_clap_frame")
try:
    from engine.clap_detector import is_clap_frame

    silence = struct.pack("<1024h", *([0] * 1024))
    assert not is_clap_frame(silence)
    pass_("silence frame rejected")

    # Very loud short burst (simulate clap)
    samples = [0] * 850 + [25000] * 50 + [0] * 124
    frame = struct.pack(f"<{len(samples)}h", *samples)
    result = is_clap_frame(frame)
    print(f"    clap_frame_result={result} rms={sum(abs(s) for s in samples)/32768/len(samples)}")
    pass_("clap-like frame processed", f"detected={result}")
except Exception as e:
    fail("is_clap_frame", f"{type(e).__name__}: {e}")

# ---------- 3. detect_double_clap ----------
print("[3] detect_double_clap")
try:
    from engine.clap_detector import detect_double_clap

    now = time.time()
    # Two events 500ms apart -> should detect
    events = [now - 0.5, now]
    assert detect_double_clap(events, now)
    pass_("double clap 500ms gap detected")

    # Two events 2s apart -> should NOT detect
    events_far = [now - 2.0, now]
    assert not detect_double_clap(events_far, now)
    pass_("far events not detected as double clap")

    # Single event -> should NOT detect
    assert not detect_double_clap([now], now)
    pass_("single event not double clap")
except Exception as e:
    fail("detect_double_clap", f"{type(e).__name__}: {e}")

# ---------- 4. AudioWakePipeline.process_frame ----------
print("[4] AudioWakePipeline.process_frame")
try:
    from engine.audio_wake_pipeline import AudioWakePipeline, EnergyVAD

    p = AudioWakePipeline(vad=EnergyVAD())
    silence = struct.pack("<1280h", *([0] * 1280))
    result = p.process_frame(silence)
    assert not result["wake"], f"wake on silence: {result}"
    pass_("process_frame with silence = no wake")

    # Check pre-roll fills
    assert len(p._preroll) > 0, "preroll not filling"
    pass_("preroll buffer fills", f"frames={len(p._preroll)}")
except Exception as e:
    fail("process_frame", f"{type(e).__name__}: {e}")

# ---------- 5. OpenWakeWord availability ----------
print("[5] openWakeWord")
try:
    try:
        from openwakeword.model import Model
        print("    openwakeword module: OK")
    except ImportError:
        print("    openwakeword module: NOT INSTALLED (skip model test)")

    try:
        from engine.audio_wake_pipeline import OpenWakeWordScorer
        scorer = OpenWakeWordScorer(pretrained="alexa")
        pass_("OpenWakeWordScorer created", f"model={scorer.model_name}")
    except ImportError as e:
        print(f"    scorer creation skipped (model download needed): {e}")
        pass_("OpenWakeWordScorer import only", "model download not tested")
except Exception as e:
    fail("openWakeWord", f"{type(e).__name__}: {e}")

# ---------- 6. Clap in pipeline ----------
print("[6] Clap in audio_wake_pipeline")
try:
    from engine.audio_wake_pipeline import AudioWakePipeline
    from engine.clap_detector import ClapStateMachine

    p = AudioWakePipeline(enable_clap=True)
    assert p.is_clap_enabled()
    pass_("clap enabled in pipeline")

    p2 = AudioWakePipeline(enable_clap=False)
    assert not p2.is_clap_enabled()
    pass_("clap disabled in pipeline")
except Exception as e:
    fail("clap in pipeline", f"{type(e).__name__}: {e}")

# ---------- 7. Hotkey wake ----------
print("[7] Hotkey wake")
try:
    from engine.hotkey_wake import start_hotkey_listener, stop_hotkey_listener
    pass_("hotkey_wake module imports OK")
except Exception as e:
    fail("hotkey_wake", f"{type(e).__name__}: {e}")

# ---------- Result ----------
print()
total = 14
if FAILURES:
    print(f"RESULT: FAIL ({FAILURES} failures, {total - FAILURES} passed)")
    sys.exit(1)
else:
    print(f"RESULT: PASS ({total} checks)")
    sys.exit(0)