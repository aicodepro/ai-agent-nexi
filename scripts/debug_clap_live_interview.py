#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import struct
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * 80 / 1000)


def _rms(pcm16: bytes) -> float:
    n = len(pcm16) // 2
    if n <= 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm16)
    return (sum(sample * sample for sample in samples) / n) ** 0.5 / 32768.0


def _pass(name: str) -> None:
    print(f"PASS {name}")


def _fail(name: str, reason: str) -> None:
    print(f"FAIL {name} reason={reason}")


def _frames(duration: float, device: int | None):
    import sounddevice as sd
    import numpy as np

    count = max(1, int(duration * SAMPLE_RATE / FRAME_SAMPLES))
    stream = sd.InputStream(device=device, channels=1, samplerate=SAMPLE_RATE, dtype=np.int16, blocksize=FRAME_SAMPLES)
    with stream:
        for _ in range(count):
            chunk, _ = stream.read(FRAME_SAMPLES)
            yield np.asarray(chunk).reshape(-1).astype(np.int16).tobytes()


def main() -> int:
    parser = argparse.ArgumentParser(description="Interview DSP double-clap live check")
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--duration", type=float, default=6.0)
    args = parser.parse_args()

    os.environ.setdefault("NEXI_CLAP_ENABLED", "true")
    os.environ["NEXI_CLAP_PRIMARY"] = "dsp_clap"
    os.environ["NEXI_CLAP_BACKEND_ORDER"] = "dsp_clap,clap_nn"
    os.environ.setdefault("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.030")
    os.environ.setdefault("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.10")
    os.environ.setdefault("NEXI_DSP_CLAP_PEAK_RATIO", "4.0")
    os.environ.setdefault("NEXI_DSP_CLAP_HF_RATIO", "0.30")
    os.environ.setdefault("NEXI_DSP_CLAP_EVENT_COOLDOWN_MS", "80")
    os.environ.setdefault("NEXI_DSP_CLAP_SPEECH_REJECT_MS", "250")
    os.environ.setdefault("NEXI_CLAP_MIN_GAP_MS", "100")
    os.environ.setdefault("NEXI_CLAP_MAX_GAP_MS", "3500")
    os.environ.setdefault("NEXI_CLAP_COOLDOWN_MS", "1500")

    from engine.clap_backend_manager import ClapBackendManager

    manager = ClapBackendManager()
    status = manager.get_status()
    print(f"active backend: {status.get('primary')} ready={status.get('primary_ready')}")
    print("Instruction: make exactly one double clap within the capture window.")

    if status.get("primary") == "dsp_clap" and status.get("primary_ready"):
        _pass("clap_backend_dsp_active")
    else:
        _fail("clap_backend_dsp_active", f"status={status}")
        return 1

    audio_seen = False
    first_seen = False
    double_seen = False
    single_woke = False
    last_reason = "no_audio"
    last_gap = None

    try:
        for frame in _frames(args.duration, args.device):
            if _rms(frame) > 0.002:
                audio_seen = True
            event = manager.process_audio_chunk(frame)
            last_reason = event.get("reject_reason") or event.get("reason") or last_reason
            if event.get("clap") and not event.get("wake"):
                first_seen = True
                print(f"first clap seen backend={event.get('backend_used')} reason={last_reason}")
            if event.get("gap_ms") is not None:
                last_gap = event.get("gap_ms")
                print(f"gap ms: {last_gap:.0f}")
            if event.get("wake"):
                double_seen = True
                print(f"second clap seen backend={event.get('backend_used')} gap_ms={event.get('gap_ms')}")
                print("wake emitted: true")
                break
    except Exception as exc:
        _fail("clap_audio_seen", f"mic_error:{type(exc).__name__}")
        return 1

    if audio_seen:
        _pass("clap_audio_seen")
    else:
        _fail("clap_audio_seen", last_reason)
    if first_seen:
        _pass("first_clap_seen")
    else:
        _fail("first_clap_seen", last_reason)
    if double_seen:
        _pass("double_clap_detected")
    else:
        _fail("double_clap_detected", f"last_reason={last_reason} gap_ms={last_gap}")
    if not single_woke:
        _pass("single_clap_no_wake")
    else:
        _fail("single_clap_no_wake", "single_clap_triggered_wake")

    return 0 if audio_seen and first_seen and double_seen and not single_woke else 1


if __name__ == "__main__":
    sys.exit(main())
