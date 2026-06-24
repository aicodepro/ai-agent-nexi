"""Automatic microphone selection.

Enumerates audio input devices, scores them (must open at the pipeline's
sample rate + a headset/quality name heuristic), picks the best, persists the
choice to config/mic_selection.json, and re-validates on every run. Falls back
to the next-best device and finally the OS default, so it can never leave the
wake pipeline without a working mic.

Public surface:
    select_best_mic(samplerate, channels) -> (best_dict | None, ranked_list)
    enumerate_input_devices(sd) -> list[dict]
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "mic_selection.json"

# Headset / personal-mic devices are preferred (close-talk = better SNR).
_HEADSET_KW = (
    "headset", "hands-free", "hands free", "handsfree", "headphone", "earbud",
    "ear buds", "earbuds", "buds", "airpod", "wh-", "wf-", "jbl", "bose",
    "beats", "galaxy buds", "skullcandy", "boat", "earphone",
)
# Built-in arrays are decent and reliably 16 kHz-capable.
_BUILTIN_KW = (
    "microphone array", "mic array", "internal microphone", "built-in",
    "realtek", "intel smart sound", "smart sound",
)
# Loopback / virtual / generic mapper devices must never be chosen.
_AVOID_KW = (
    "stereo mix", "what u hear", "loopback", "sound mapper",
    "primary sound capture", "wave", "line in", "spdif", "virtual",
    "voicemeeter", "cable output", "vb-audio",
)


def _safe_log(msg: str) -> None:
    try:
        from engine.debug_trace import line
        line(msg)
    except Exception:
        print(msg, flush=True)


def enumerate_input_devices(sd) -> list[dict]:
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0:
            devices.append({
                "index": index,
                "name": info.get("name", ""),
                "channels": int(info.get("max_input_channels", 0)),
                "default_samplerate": int(info.get("default_samplerate", 0) or 0),
            })
    return devices


def _can_open(sd, index: int, samplerate: int, channels: int) -> bool:
    """Verify the device actually opens with the pipeline's exact stream config."""
    try:
        stream = sd.InputStream(
            samplerate=samplerate, channels=channels, dtype="float32",
            blocksize=int(samplerate * 0.08), device=index,
        )
        stream.start()
        stream.stop()
        stream.close()
        return True
    except Exception:
        return False


def _name_score(name: str, prefer_headset: bool) -> int:
    n = (name or "").lower()
    if any(k in n for k in _AVOID_KW):
        return -1000
    score = 50
    is_headset = any(k in n for k in _HEADSET_KW)
    if is_headset:
        score += 40 if prefer_headset else -10
    elif any(k in n for k in _BUILTIN_KW):
        score += 20
    return score


def select_best_mic(samplerate: int = 16000, channels: int = 1, probe: bool = True):
    """Return (best_device|None, ranked_devices). Persists the result."""
    import sounddevice as sd

    prefer_headset = (os.getenv("NEXI_MIC_PREFER_HEADSET", "true") or "").strip().lower() in {"1", "true", "yes", "on"}
    ranked = []
    for dev in enumerate_input_devices(sd):
        score = _name_score(dev["name"], prefer_headset)
        openable = _can_open(sd, dev["index"], samplerate, channels) if (probe and score > -1000) else (score > -1000)
        if not openable:
            score = -1000
        ranked.append({**dev, "score": score, "openable": bool(openable)})

    ranked.sort(key=lambda d: (d["score"], -d["index"]), reverse=True)
    best = next((d for d in ranked if d["score"] > 0 and d["openable"]), None)
    _persist(ranked, best, samplerate)
    return best, ranked


def _persist(ranked: list[dict], best: dict | None, samplerate: int) -> None:
    try:
        _CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG.write_text(
            json.dumps({"samplerate": samplerate, "selected": best, "ranked": ranked}, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        _safe_log(f"[MIC] persist_failed reason={type(exc).__name__}")
