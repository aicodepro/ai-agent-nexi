"""YAMNet-based clap event detector.

Uses TensorFlow Hub YAMNet for pretrained audio event classification.
Detects AudioSet labels: "Clapping", "Applause".
Rejects speech labels.

If TensorFlow / TensorFlow Hub is not installed, this backend reports
not_ready and does not crash. Runtime falls through to dsp_clap.

Config env vars:
  JARVIS_YAMNET_CLAP_ENABLED=true
  JARVIS_YAMNET_CLAP_THRESHOLD=0.35
  JARVIS_YAMNET_SPEECH_REJECT_THRESHOLD=0.25
  JARVIS_YAMNET_DEBUG=false
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


_CLAP_LABELS = {"clapping", "applause"}
_SPEECH_LABELS = {
    "speech", "conversation", "narration", "monologue",
    "whispering", "shout", "yelling",
}


@dataclass
class YamnetClapResult:
    is_clap: bool
    confidence: float
    timestamp: float
    top_labels: list[tuple[str, float]]
    reason: str


class YamnetClapBackend:
    """YAMNet-based clap detector using TensorFlow Hub.

    Falls back to not_ready if TF/TF-Hub is not installed, without crashing
    the runtime.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        clock: Callable[[], float] | None = None,
    ):
        self._sample_rate = sample_rate
        self._clock = clock or time.time
        self._debug = _env_bool("JARVIS_YAMNET_DEBUG", False)
        self._threshold = _env_float("JARVIS_YAMNET_CLAP_THRESHOLD", 0.35)
        self._speech_reject = _env_float("JARVIS_YAMNET_SPEECH_REJECT_THRESHOLD", 0.25)

        self._model = None
        self._model_loaded = False
        self._load_error = ""
        self._class_names: list[str] = []

        self._load_model()

    def _load_model(self) -> None:
        try:
            import tensorflow as tf
            import tensorflow_hub as hub
        except ImportError as e:
            self._load_error = f"tf_not_installed:{type(e).__name__}"
            if self._debug:
                print(f"[YAMNET] not_ready reason={self._load_error}", flush=True)
            return

        try:
            model_url = "https://tfhub.dev/google/yamnet/1"
            self._model = hub.load(model_url)
            class_map_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "models", "yamnet", "yamnet_class_map.csv",
            )
            if os.path.isfile(class_map_path):
                with open(class_map_path) as f:
                    self._class_names = [line.strip().split(",")[-1] for line in f if line.strip()]
            self._model_loaded = True
            if self._debug:
                print(f"[YAMNET] model_loaded=true classes={len(self._class_names)}", flush=True)
        except Exception as e:
            self._load_error = f"load_failed:{type(e).__name__}"
            if self._debug:
                print(f"[YAMNET] not_ready reason={self._load_error}", flush=True)

    @property
    def ready(self) -> bool:
        return self._model_loaded

    def process_pcm16(self, pcm16: bytes, timestamp: float | None = None) -> YamnetClapResult:
        now = timestamp if timestamp is not None else self._clock()

        if not self._model_loaded:
            return YamnetClapResult(
                is_clap=False, confidence=0.0, timestamp=now,
                top_labels=[], reason=f"not_ready:{self._load_error}",
            )

        try:
            import numpy as np
            import tensorflow as tf

            waveform = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            scores, embeddings, spectrogram = self._model(waveform)
            scores = scores.numpy()

            mean_scores = scores.mean(axis=0)
            top_indices = mean_scores.argsort()[-5:][::-1]

            top_labels = []
            for idx in top_indices:
                label = self._class_names[idx] if idx < len(self._class_names) else f"class_{idx}"
                top_labels.append((label, float(mean_scores[idx])))

            clap_conf = 0.0
            speech_conf = 0.0
            for label, conf in top_labels:
                label_lower = label.strip().lower()
                if label_lower in _CLAP_LABELS:
                    clap_conf = max(clap_conf, conf)
                if label_lower in _SPEECH_LABELS:
                    speech_conf = max(speech_conf, conf)

            is_clap = False
            reason = "none"
            if speech_conf >= self._speech_reject:
                is_clap = False
                reason = f"speech_reject speech={speech_conf:.2f}"
            elif clap_conf >= self._threshold:
                is_clap = True
                reason = f"clap_detected clap={clap_conf:.2f}"
            else:
                reason = f"below_threshold clap={clap_conf:.2f} speech={speech_conf:.2f}"

            if self._debug:
                top_str = " ".join(f"{l}:{c:.2f}" for l, c in top_labels[:3])
                print(
                    f"[YAMNET_CLAP] top={top_str} "
                    f"is_clap={str(is_clap).lower()} reason={reason}",
                    flush=True,
                )

            return YamnetClapResult(
                is_clap=is_clap,
                confidence=clap_conf if is_clap else 0.0,
                timestamp=now,
                top_labels=top_labels,
                reason=reason,
            )
        except Exception as e:
            return YamnetClapResult(
                is_clap=False, confidence=0.0, timestamp=now,
                top_labels=[], reason=f"inference_error:{type(e).__name__}",
            )

    def reset(self) -> None:
        pass

    def get_status(self) -> dict:
        return {
            "enabled": self._model_loaded,
            "backend": "yamnet",
            "ready": self._model_loaded,
            "threshold": self._threshold,
            "speech_reject_threshold": self._speech_reject,
            "sample_rate": self._sample_rate,
            "load_error": self._load_error,
        }

    def get_debug_snapshot(self) -> dict:
        return self.get_status()
