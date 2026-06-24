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
        self._warned = False

    def load(self) -> bool:
        if self._loaded:
            return True
        try:
            import torch
            hub_dir = torch.hub.get_dir()
            local_repo = None
            for name in ("snakers4_silero-vad_master", "snakers4_silero-vad_main"):
                cand = os.path.join(hub_dir, name)
                if os.path.isdir(cand):
                    local_repo = cand
                    break
            if local_repo:
                model, _ = torch.hub.load(local_repo, "silero_vad",
                                          source="local", trust_repo=True)
            else:
                model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad",
                                          force_reload=False, trust_repo=True)
            self._model = model
            self._loaded = True
            print(f"[VAD] silero loaded ({'local cache' if local_repo else 'github'})", flush=True)
            return True
        except Exception as e:
            print(f"[VAD] silero_load_failed reason={type(e).__name__}: {e}", flush=True)
            return False

    def is_speech(self, frame_int16, sample_rate: int = 16000) -> bool:
        if not self._model:
            return False
        try:
            import torch
            import numpy as np
            window = 512 if sample_rate >= 16000 else 256
            audio = np.frombuffer(frame_int16, dtype=np.int16).astype(np.float32) / 32768.0
            if audio.shape[0] < window:
                return False
            n_windows = audio.shape[0] // window
            for i in range(n_windows):
                chunk = torch.from_numpy(audio[i * window:(i + 1) * window])
                if self._model(chunk, sample_rate).item() > self._threshold:
                    return True
            return False
        except Exception as e:
            if not self._warned:
                self._warned = True
                print(f"[VAD] silero_infer_failed reason={type(e).__name__}: {e}", flush=True)
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
