"""OpenWakeWord hotword detector."""

import os
import time
from core.config import cfg, env_float, env_int


class HotwordDetector:
    def __init__(self):
        self._model = None
        self._phrases = self._resolve_phrases()
        self._threshold = env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25)
        self._consecutive_required = env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 1)
        self._cooldown_s = cfg.wake_cooldown_ms / 1000.0
        self._min_rms = env_float("HOTWORD_MIN_RMS", 0.004)
        self._rising_edge_delta = env_float("HOTWORD_RISING_EDGE_DELTA", 0.03)

        self._consecutive_hits = 0
        self._last_score = 0.0
        self._last_detection_time = 0.0
        self._loaded = False

    def _resolve_phrases(self) -> list:
        env = os.getenv("OPENWAKEWORD_PHRASES", "hey_nexi,nexi").strip()
        return [p.strip().lower().replace(" ", "_") for p in env.split(",") if p.strip()]

    def _ensure_base_models(self) -> None:
        """Download OpenWakeWord's shared feature models if they're missing.

        The melspectrogram + embedding models are required for any wake model
        to load. A fresh install ships without them, which previously caused a
        NoSuchFile error at load time.
        """
        try:
            import openwakeword
            from pathlib import Path
            mdir = Path(openwakeword.__file__).parent / "resources" / "models"
            needed = ["melspectrogram.onnx", "embedding_model.onnx"]
            if all((mdir / f).is_file() for f in needed):
                return
            print("[HOTWORD] base models missing, downloading...", flush=True)
            from openwakeword import utils
            utils.download_models()
            print("[HOTWORD] base models downloaded", flush=True)
        except Exception as e:
            print(f"[HOTWORD] base_model_download_failed reason={type(e).__name__}", flush=True)

    def load(self) -> bool:
        if self._loaded:
            return True
        try:
            self._ensure_base_models()
            from openwakeword.model import Model
            model_path = os.getenv("OPENWAKEWORD_MODEL_PATH", "").strip()
            if model_path and os.path.isfile(model_path):
                # Custom-trained model (e.g. a "hey nexi" model).
                self._model = Model(wakeword_models=[model_path], inference_framework="onnx")
                print(f"[HOTWORD] loaded custom model={os.path.basename(model_path)} "
                      f"phrases={self._phrases}", flush=True)
            else:
                if model_path:
                    print(f"[HOTWORD] model_path not found: {model_path} — "
                          f"falling back to bundled models", flush=True)
                self._model = Model(inference_framework="onnx")
                print(f"[HOTWORD] loaded bundled models phrases={self._phrases}", flush=True)
                # If none of the requested phrases map to a loaded model (e.g. no
                # custom "hey_nexi" model is installed), fall back to a bundled
                # model so voice wake still works out-of-the-box.
                try:
                    available = [k.lower() for k in self._model.models.keys()]
                    if not any(any(p in k for k in available) for p in self._phrases):
                        fallback = os.getenv("OPENWAKEWORD_FALLBACK_MODEL", "hey_nexi").lower()
                        chosen = next((k for k in available if fallback in k),
                                      available[0] if available else "")
                        if chosen:
                            self._phrases = [chosen]
                            print(f"[HOTWORD] no model for requested phrase; falling back to "
                                  f"bundled '{chosen}'. Say it to wake, or set "
                                  f"OPENWAKEWORD_MODEL_PATH to a custom 'hey nexi' model.",
                                  flush=True)
                        else:
                            print("[HOTWORD] WARNING: no bundled models available; "
                                  "voice wake will not fire (use double clap).", flush=True)
                except Exception:
                    pass
            self._loaded = True
            return True
        except Exception as e:
            print(f"[HOTWORD] load_failed reason={type(e).__name__}: {e}", flush=True)
            return False

    def score(self, frame_int16) -> float:
        if not self._model:
            return 0.0
        try:
            import numpy as np
            audio = np.frombuffer(frame_int16, dtype=np.int16)
            predictions = self._model.predict(audio)
            if isinstance(predictions, dict):
                relevant = {k: v for k, v in predictions.items()
                            if any(p in k.lower() for p in self._phrases)}
                # Only score the requested wake phrase(s). If none of the loaded
                # models match the configured phrase, return 0 rather than the
                # max across all models — otherwise any wake word (or noise on
                # an unrelated model) would trigger a false wake.
                if relevant:
                    return max(relevant.values())
                return 0.0
            return 0.0
        except Exception:
            return 0.0

    def process_frame(self, frame_int16, sample_rate: int = 16000) -> dict:
        """Process one audio frame. Returns {detected, score, reason}."""
        import struct
        import math

        result = {"detected": False, "score": 0.0, "source": "hotword", "reason": ""}

        # RMS gate
        n_samples = len(frame_int16) // 2
        if n_samples > 0:
            samples = struct.unpack(f"<{n_samples}h", frame_int16)
            rms = math.sqrt(sum(s * s for s in samples) / n_samples) / 32768.0
            if rms < self._min_rms:
                self._consecutive_hits = 0
                result["reason"] = "below_rms"
                return result

        # Cooldown
        now = time.time()
        if now - self._last_detection_time < self._cooldown_s:
            result["reason"] = "cooldown"
            return result

        # Score
        current_score = self.score(frame_int16)
        result["score"] = current_score

        if current_score < self._threshold:
            self._consecutive_hits = 0
            self._last_score = current_score
            result["reason"] = "below_threshold"
            return result

        # Rising edge check
        if current_score - self._last_score < self._rising_edge_delta:
            self._last_score = current_score
            result["reason"] = "no_rising_edge"
            return result

        self._last_score = current_score
        self._consecutive_hits += 1

        if self._consecutive_hits >= self._consecutive_required:
            self._consecutive_hits = 0
            self._last_detection_time = now
            result["detected"] = True
            result["reason"] = "hotword_detected"

        return result

    def reset(self):
        self._consecutive_hits = 0
        self._last_score = 0.0
