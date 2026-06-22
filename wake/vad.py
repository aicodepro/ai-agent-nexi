"""Voice Activity Detection — Silero (primary) + Energy (fallback)."""

import math
import struct
import os
from core.config import env_float, env_int


class EnergyVAD:
    """Simple RMS energy-based VAD. Always available."""

    def __init__(self, threshold: float = 0.01):
        self._threshold = threshold

    def is_speech(self, frame_int16, sample_rate: int = 16000) -> bool:
        n = len(frame_int16) // 2
        if n == 0:
            return False
        samples = struct.unpack(f"<{n}h", frame_int16)
        rms = math.sqrt(sum(s * s for s in samples) / n) / 32768.0
        return rms > self._threshold


class SileroVAD:
    """Silero neural VAD via torch."""

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._model = None
        self._loaded = False

    def load(self) -> bool:
        if self._loaded:
            return True
        try:
            import torch
            model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad",
                                          force_reload=False, trust_repo=True)
            self._model = model
            self._loaded = True
            print("[VAD] silero loaded", flush=True)
            return True
        except Exception as e:
            print(f"[VAD] silero_load_failed reason={type(e).__name__}", flush=True)
            return False

    def is_speech(self, frame_int16, sample_rate: int = 16000) -> bool:
        if not self._model:
            return False
        try:
            import torch
            import numpy as np
            audio = np.frombuffer(frame_int16, dtype=np.int16).astype(np.float32) / 32768.0
            tensor = torch.from_numpy(audio)
            prob = self._model(tensor, sample_rate).item()
            return prob > self._threshold
        except Exception:
            return False


def create_vad() -> EnergyVAD | SileroVAD:
    """Create the best available VAD."""
    backend = os.getenv("VAD_BACKEND", "silero").strip().lower()
    if backend == "silero":
        vad = SileroVAD(
            threshold=env_float("VAD_THRESHOLD", 0.5),
            sample_rate=env_int("AUDIO_SAMPLE_RATE", 16000),
        )
        if vad.load():
            return vad
        print("[VAD] silero unavailable, falling back to energy VAD", flush=True)
    return EnergyVAD(threshold=env_float("VAD_ENERGY_THRESHOLD", 0.01))
