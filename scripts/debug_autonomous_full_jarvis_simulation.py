#!/usr/bin/env python3
"""Synthetic full Jarvis wake + UI validation without cloud or microphone."""

from __future__ import annotations

import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, sec: float) -> None:
        self.t += sec


class Scores:
    def __init__(self, values):
        self.values = list(values)
        self.i = 0

    def __call__(self, audio):
        value = self.values[min(self.i, len(self.values) - 1)] if self.values else 0.0
        self.i += 1
        return value


def pcm(samples) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def silence_frame() -> bytes:
    return b"\x00\x00" * FRAME_SAMPLES


def speech_like_frame() -> bytes:
    samples = []
    for i in range(FRAME_SAMPLES):
        val = 0.08 * math.sin(2 * math.pi * 180 * i / SAMPLE_RATE) + 0.04 * math.sin(2 * math.pi * 420 * i / SAMPLE_RATE)
        samples.append(int(val * 32767))
    return pcm(samples)


def voice_like_frame() -> bytes:
    return pcm([900, -900] * (FRAME_SAMPLES // 2))


def clap_frame(total: int = FRAME_SAMPLES) -> bytes:
    samples = [0] * total
    start = total * 3 // 4
    for i in range(200):
        idx = start + i
        if idx >= total:
            break
        val = (
            math.sin(2 * math.pi * 3500 * i / SAMPLE_RATE) * 0.4
            + math.sin(2 * math.pi * 5000 * i / SAMPLE_RATE) * 0.4
            + math.sin(2 * math.pi * 7000 * i / SAMPLE_RATE) * 0.4
        )
        val *= (1.0 - i / 200) * 0.6
        samples[idx] = int(val * 32767)
    return pcm(samples)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL synthetic {message}")
        raise SystemExit(1)


def main() -> int:
    os.environ.setdefault("JARVIS_CLAP_BACKEND_ORDER", "dsp_clap")
    os.environ.setdefault("JARVIS_DSP_CLAP_RMS_THRESHOLD", "0.045")
    os.environ.setdefault("JARVIS_DSP_CLAP_PEAK_THRESHOLD", "0.14")
    os.environ.setdefault("JARVIS_DSP_CLAP_PEAK_RATIO", "5.2")
    os.environ.setdefault("JARVIS_DSP_CLAP_HF_RATIO", "0.43")
    os.environ.setdefault("JARVIS_DSP_CLAP_EVENT_COOLDOWN_MS", "120")
    os.environ.setdefault("JARVIS_CLAP_MIN_GAP_MS", "160")
    os.environ.setdefault("JARVIS_CLAP_MAX_GAP_MS", "950")

    before_modules = set(sys.modules)

    from engine.hotword_engine_manager import HotwordEngineManager
    from engine.clap_backend_manager import ClapBackendManager
    from engine.ui_state_manager import UIStateManager

    # Silence: no hotword and no double-clap wake.
    hotword_silence = HotwordEngineManager({
        "scorer": Scores([0.0]),
        "threshold": 0.25,
        "enforce_rms_gate": True,
    })
    assert_true(not hotword_silence.process_audio_chunk(silence_frame(), SAMPLE_RATE).detected, "silence hotword wake")
    clock = Clock()
    clap_mgr = ClapBackendManager(clock=clock, cooldown_ms=1800)
    assert_true(not clap_mgr.process_audio_chunk(silence_frame()).get("wake"), "silence clap wake")
    print("PASS synthetic silence no wake")

    # Random speech-like audio must not wake as clap.
    for _ in range(6):
        clock.advance(0.08)
        result = clap_mgr.process_audio_chunk(speech_like_frame())
        assert_true(not result.get("wake"), "speech clap wake")
    print("PASS synthetic speech no clap wake")

    # Hotword wake with realistic RMS and injected local scorer.
    hotword = HotwordEngineManager({
        "scorer": Scores([0.8]),
        "threshold": 0.25,
        "enforce_rms_gate": True,
    })
    assert_true(hotword.process_audio_chunk(voice_like_frame(), SAMPLE_RATE).detected, "hotword did not wake")
    print("PASS synthetic hotword wake")

    # Single clap must not wake.
    clap_mgr.reset()
    clock.advance(10.0)
    single = clap_mgr.process_audio_chunk(clap_frame())
    assert_true(single.get("clap") is True and single.get("wake") is False, "single clap woke")
    print("PASS synthetic single clap no wake")

    # Double clap must wake.
    clock.advance(0.24)
    double = clap_mgr.process_audio_chunk(clap_frame())
    assert_true(double.get("wake") is True and double.get("source") == "double_clap", "double clap missed")
    print("PASS synthetic double clap wake")

    # UI flow and synthetic ASR/response/TTS lifecycle.
    ui = UIStateManager(dedupe_ms=0)
    flow_states = []
    for state, source, text in (
        ("sleep", "system", ""),
        ("wake_detected", "hotword", ""),
        ("listening", "hotword", ""),
        ("recognising", "asr", ""),
        ("thinking", "assistant", "open notepad"),
        ("saying", "tts", "Opening Notepad."),
        ("sleep", "system", ""),
    ):
        event = ui.emit(state, source=source, text=text)
        if event:
            flow_states.append(event.state)
    assert_true(flow_states == ["sleep", "wake_detected", "listening", "recognising", "thinking", "saying", "sleep"], f"bad UI flow {flow_states}")
    print("PASS synthetic UI flow sleep→wake_detected→listening→recognising→thinking→saying→sleep")

    duplicate_ui = UIStateManager(dedupe_ms=250)
    assert_true(duplicate_ui.emit("listening", source="hotword") is not None, "first duplicate test failed")
    assert_true(duplicate_ui.emit("listening", source="hotword") is None, "duplicate state not deduped")
    print("PASS synthetic no duplicate state events")

    after_modules = set(sys.modules)
    loaded_cloud = sorted(m for m in (after_modules - before_modules) if m in {"engine.groq_asr", "engine.groq_tts"})
    assert_true(not loaded_cloud, f"Groq loaded before wake {loaded_cloud}")
    print("PASS synthetic no Groq before wake")

    empty_ui = UIStateManager(dedupe_ms=0)
    empty_ui.emit("recognising", source="asr")
    empty = empty_ui.emit("sleep", source="asr", status="empty_asr")
    assert_true(empty is not None and empty.state == "sleep", "ASR empty did not return sleep")
    print("PASS synthetic ASR empty returns sleep")

    tts_ui = UIStateManager(dedupe_ms=0)
    saying = tts_ui.emit("saying", source="tts")
    sleep = tts_ui.emit("sleep", source="tts", status="tts_done")
    assert_true(saying is not None and saying.state == "saying" and sleep is not None and sleep.state == "sleep", "TTS saying/sleep flow bad")
    print("PASS synthetic TTS saying then sleep")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
