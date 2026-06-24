from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RATE = 16000
FRAME_MS = 80
CHUNK = int(RATE * FRAME_MS / 1000)
SINGLE_ATTEMPTS = 10
DOUBLE_ATTEMPTS = 10
SINGLE_LISTEN_SECONDS = 1.2
DOUBLE_LISTEN_SECONDS = 1.5


def _listen_attempt(stream, manager, seconds: float) -> dict:
    start = time.time()
    claps = []
    wake = False
    backend = "none"
    last_gap = None
    while time.time() - start < seconds:
        data, _overflow = stream.read(CHUNK)
        frame = bytes(data)
        event = manager.process_audio_chunk(frame)
        if event.get("clap"):
            ts = time.time() - start
            claps.append(ts)
            backend = event.get("backend", backend)
            last_gap = event.get("gap_ms")
            gap_text = "-" if last_gap is None else f"{last_gap:.0f}"
            if event.get("wake"):
                print(f"[CLAP] second_clap gap_ms={gap_text}")
            else:
                print(f"[CLAP] single_clap backend={backend} wake=false gap_ms={gap_text}")
                print("[CLAP] waiting_for_second_clap")
        if event.get("wake"):
            wake = True
            print("[CLAP] double_clap_detected=true wake_candidate=true")
    return {"claps": claps, "wake": wake, "backend": backend, "gap_ms": last_gap}


def main() -> int:
    print("Nexi double-clap calibration")
    print("Local-only: no Groq, Gemini, cloud ASR, or cloud TTS is used for clap detection.")
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"[CLAP_CAL] missing_audio_dependency reason={type(exc).__name__}")
        return 1

    from engine.clap_backend_manager import ClapBackendManager

    manager = ClapBackendManager(cooldown_ms=0)
    print(f"[CLAP_CAL] status={manager.get_status()}")
    single_wakes = 0
    double_wakes = 0
    double_gaps: list[float] = []

    try:
        with sd.RawInputStream(samplerate=RATE, channels=1, blocksize=CHUNK, dtype="int16") as stream:
            for index in range(1, SINGLE_ATTEMPTS + 1):
                manager.reset()
                input(f"Press Enter, then do ONE clap attempt {index}/{SINGLE_ATTEMPTS}...")
                result = _listen_attempt(stream, manager, SINGLE_LISTEN_SECONDS)
                single_wakes += 1 if result["wake"] else 0
                print(f"[CLAP_CAL] single attempt={index} claps={len(result['claps'])} wake={result['wake']} gap_ms={result['gap_ms']}")

            for index in range(1, DOUBLE_ATTEMPTS + 1):
                manager.reset()
                input(f"Press Enter, then do TWO claps attempt {index}/{DOUBLE_ATTEMPTS}...")
                result = _listen_attempt(stream, manager, DOUBLE_LISTEN_SECONDS)
                double_wakes += 1 if result["wake"] else 0
                if result["gap_ms"] is not None:
                    double_gaps.append(float(result["gap_ms"]))
                print(f"[CLAP_CAL] double attempt={index} claps={len(result['claps'])} wake={result['wake']} gap_ms={result['gap_ms']}")
    except KeyboardInterrupt:
        print("[CLAP_CAL] stopped_by_user")
        return 2
    except Exception as exc:
        print(f"[CLAP_CAL] failed reason={type(exc).__name__}")
        return 1

    print("\nCalibration report")
    print(f"single_clap_wakes={single_wakes}/{SINGLE_ATTEMPTS}")
    print(f"double_clap_wakes={double_wakes}/{DOUBLE_ATTEMPTS}")
    if double_gaps:
        print(f"gap_ms_min={min(double_gaps):.0f} gap_ms_avg={statistics.mean(double_gaps):.0f} gap_ms_max={max(double_gaps):.0f}")
    print("Recommended env:")
    print("NEXI_CLAP_ENABLED=true")
    print("NEXI_CLAP_BACKEND_ORDER=tzur,nexi")
    print("NEXI_CLAP_PATTERN=double")
    print("NEXI_CLAP_MIN_GAP_MS=180")
    print("NEXI_DOUBLE_CLAP_WINDOW_MS=900")
    print("NEXI_CLAP_COOLDOWN_MS=2000")
    if single_wakes == 0 and double_wakes >= 8:
        print("PASS")
        return 0
    print("PARTIAL: tune clap gap/window/threshold values from the printed events.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
