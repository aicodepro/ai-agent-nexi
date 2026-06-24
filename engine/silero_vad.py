# silero_vad.py
#
# Voice-activity detection for command capture.
#
# Backed by the Silero VAD ONNX model that ships *inside* the openWakeWord
# package (resources/models/silero_vad.onnx), so no extra dependency or model
# download is required — onnxruntime is already a transitive dependency of
# openWakeWord. If that model/runtime is unavailable for any reason, an
# energy-based fallback keeps command capture working instead of crashing.
#
# Public surface (matches what AudioWakePipeline.capture_command expects):
#   SileroVAD().is_speech(frame_int16: bytes) -> bool
#   SileroVAD().reset() -> None

from __future__ import annotations

import os


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _safe_log(msg: str) -> None:
    try:
        from engine.debug_trace import line
        line(msg)
    except Exception:
        print(msg, flush=True)


class SileroVAD:
    """Streaming Silero VAD wrapper with an energy-based fallback.

    The input contract is 16 kHz, mono, 16-bit PCM (int16) bytes — the same
    format the wake pipeline pushes onto its frame queue.
    """

    name = "silero"

    def __init__(self, threshold: float | None = None, frame_size: int = 640):
        self._threshold = (
            float(threshold) if threshold is not None else _env_float("VAD_THRESHOLD", 0.35)
        )
        # 640 samples = 40 ms @ 16 kHz, and 1280 / 640 = 2 — it divides the
        # wake frame EVENLY so no zero-padding is ever appended. Padding (e.g.
        # at 512, which leaves a 256-sample remainder) corrupts Silero's
        # recurrent ONNX state and locks the score high, so the model never
        # reports end-of-speech silence and capture runs to the max ceiling.
        self._frame_size = int(frame_size)
        self._rms_floor = _env_float("VAD_FALLBACK_RMS", 0.012)
        self._vad = None
        self._mode = "silero"

        try:
            from openwakeword.vad import VAD  # bundled Silero ONNX
            self._vad = VAD()
            _safe_log(f"[VAD] backend=silero threshold={self._threshold}")
        except Exception as exc:  # pragma: no cover - depends on install
            self._mode = "energy"
            _safe_log(
                f"[VAD] silero_unavailable reason={type(exc).__name__}; using energy fallback"
            )

    def is_speech(self, frame_int16: bytes) -> bool:
        if not frame_int16:
            return False
        try:
            import numpy as np

            samples = np.frombuffer(frame_int16, dtype=np.int16)
            if samples.size == 0:
                return False

            if self._mode == "silero" and self._vad is not None:
                # Silero scores speech high (~0.7) and ambient noise / silence
                # low (~0.05 / ~0.025), so it correctly detects end-of-speech
                # silence and won't record until the max-duration ceiling the
                # way a raw energy gate does in a noisy room.
                remainder = samples.size % self._frame_size
                if remainder:
                    pad = np.zeros(self._frame_size - remainder, dtype=np.int16)
                    samples = np.concatenate([samples, pad])
                prob = float(self._vad.predict(samples, frame_size=self._frame_size))
                return prob >= self._threshold

            # Energy fallback only when the Silero ONNX model is unavailable.
            rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) / 32768.0
            return rms >= self._rms_floor
        except Exception as exc:
            _safe_log(f"[VAD] is_speech_failed reason={type(exc).__name__}")
            # Fail open so a transient error never silently drops the command.
            return True

    def reset(self) -> None:
        try:
            if self._vad is not None and hasattr(self._vad, "reset_states"):
                self._vad.reset_states()
        except Exception:
            pass
