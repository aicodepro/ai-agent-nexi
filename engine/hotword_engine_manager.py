from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default
def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default
def _safe_log(message: str) -> None:
    print(message, flush=True)
def _normalise_oww_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    if any(sep in value for sep in ("/", "\\")) or value.endswith((".onnx", ".tflite")):
        return value
    return value.replace("_", " ").lower()
def _normalise_oww_list(value: str) -> str:
    names = [_normalise_oww_name(item) for item in (value or "").split(",")]
    return ",".join(item for item in names if item)
@dataclass
class HotwordResult:
    detected: bool
    engine: str
    phrase: str
    score: float
    threshold: float
    latency_ms: float
    reason: str
class HotwordEngineManager:
    """Local-only wake word manager for openWakeWord-backed detection.

    This class never calls cloud providers. It only scores already-captured mic
    chunks and reports whether a wake phrase was detected.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", _env_bool("JARVIS_HOTWORD_ENABLED", True)))
        self.phrases = _normalise_oww_list(str(self.config.get("phrases", os.getenv("JARVIS_HOTWORD_PHRASES", os.getenv("JARVIS_HOTWORD_PHRASE", "hey jarvis,jarvis")))))
        self.phrase = _normalise_oww_name(str(self.config.get("phrase", (self.phrases.split(",") or ["hey jarvis"])[0] or "hey jarvis")))
        self.sample_rate = int(self.config.get("sample_rate", _env_int("JARVIS_WAKE_SAMPLE_RATE", _env_int("AUDIO_SAMPLE_RATE", 16000))))
        self.frame_ms = int(self.config.get("frame_ms", _env_int("JARVIS_WAKE_FRAME_MS", 80)))
        self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25)))
        self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 1)))
        self.cooldown_ms = int(self.config.get("cooldown_ms", _env_int("JARVIS_HOTWORD_COOLDOWN_MS", _env_int("OPENWAKEWORD_COOLDOWN_MS", _env_int("WAKE_COOLDOWN_MS", 1500)))))
        self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.003)))
        self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.02)))
        self.model_path = str(self.config.get("model_path", os.getenv("OPENWAKEWORD_MODEL_PATH", "")) or "")
        self.pretrained = _normalise_oww_list(str(self.config.get("pretrained", os.getenv("OPENWAKEWORD_PRETRAINED_MODELS", self.phrase)) or self.phrase))
        self.debug = bool(self.config.get("debug", _env_bool("JARVIS_WAKE_DEBUG", False) or _env_bool("OPENWAKEWORD_DEBUG", False)))
        self._clock: Callable[[], float] = self.config.get("clock", time.time)
        self._scorer = self.config.get("scorer")
        self._model = None
        self._model_name = "unloaded"
        self._configured_names: list[str] = []
        self._last_prediction_keys: list[str] = []
        self._last_prediction_key = ""
        self._last_predictions: dict[str, float] = {}
        self._consecutive_hits = 0
        self._last_detected_at = 0.0
        self._last_score_at = 0.0
        self._prev_score = 0.0
        self._load_error = ""
        self._max_score = 0.0
        self._score_frames = 0

        if self.enabled and self._scorer is None:
            self._load_openwakeword()

        if self.debug:
            self.log_status()

    def _load_openwakeword(self) -> None:
        try:
            from openwakeword.model import Model as OwwModel  # type: ignore
            try:
                from openwakeword.utils import download_models
                download_models()
            except Exception:
                pass
            if self.model_path and os.path.exists(self.model_path):
                self._model = OwwModel(wakeword_models=[self.model_path], inference_framework="onnx")
                self._model_name = os.path.basename(self.model_path)
                self._configured_names = [_normalise_oww_name(self._model_name)]
            else:
                models = [_normalise_oww_name(m) for m in self.pretrained.split(",") if m.strip()]
                self._model = OwwModel(wakeword_models=models or [self.phrase], inference_framework="onnx")
                self._model_name = (models or [self.phrase])[0]
                self._configured_names = models or [self.phrase]
        except Exception as exc:
            self._load_error = type(exc).__name__
            self._model = None
            self._model_name = "unavailable"

    def _score(self, audio_chunk: bytes) -> float:
        if self._scorer is not None:
            return float(self._scorer(audio_chunk) if callable(self._scorer) else self._scorer.score(audio_chunk))
        if self._model is None:
            return 0.0
        try:
            import numpy as np
            samples = np.frombuffer(audio_chunk, dtype=np.int16)
            predictions = self._model.predict(samples)
            if isinstance(predictions, dict):
                cleaned = {str(k): float(v) for k, v in predictions.items()}
                self._last_predictions = cleaned
                self._last_prediction_keys = sorted(cleaned.keys())
                if not cleaned:
                    self._last_prediction_key = ""
                    return 0.0
                configured = {_normalise_oww_name(name) for name in self._configured_names}
                selected = ""
                for key in cleaned:
                    if _normalise_oww_name(key) in configured:
                        selected = key
                        break
                if not selected:
                    selected = max(cleaned, key=cleaned.get)
                self._last_prediction_key = selected
                return float(cleaned.get(selected, 0.0))
            return float(predictions)
        except Exception as exc:
            self._load_error = type(exc).__name__
            return 0.0

    def process_audio_chunk(self, audio_chunk: bytes, sample_rate: int) -> HotwordResult:
        start = self._clock()
        if not self.enabled:
            return self._result(False, 0.0, start, "disabled")
        from engine.wake_session_manager import get_session_manager
        get_session_manager().check_timeout()
        if sample_rate != self.sample_rate:
            return self._result(False, 0.0, start, f"sample_rate_mismatch:{sample_rate}")
        if not audio_chunk:
            return self._result(False, 0.0, start, "empty_chunk")

        score = self._score(audio_chunk)

        # Compute RMS of audio chunk
        rms = 0.0
        try:
            import numpy as np
            samples = np.frombuffer(audio_chunk, dtype=np.int16)
            if len(samples) > 0:
                rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) / 32768.0
        except Exception:
            pass

        detected = False
        reason = "below_threshold"

        # RMS gate — reject if too quiet (silence/fan noise)
        self._max_score = max(self._max_score, score)
        self._score_frames += 1

        enforce_rms_gate = bool(self.config.get("enforce_rms_gate", self._scorer is None))
        if enforce_rms_gate and rms < self.min_rms:
            reason = f"low_rms_{rms:.5f}"
            self._consecutive_hits = 0
            self._prev_score = score
        elif score >= self.threshold:
            # Rising edge gate — require score increase from previous frame
            rising_edge = (score - self._prev_score) >= self.rising_edge_delta or self._prev_score == 0.0
            self._prev_score = score
            if not rising_edge:
                reason = "no_rising_edge"
                self._consecutive_hits = 0
            else:
                self._consecutive_hits += 1
                if self._consecutive_hits >= self.consecutive_hits_required:
                    now = self._clock()
                    if (now - self._last_detected_at) * 1000.0 < self.cooldown_ms:
                        reason = "cooldown"
                        self._consecutive_hits = 0
                    else:
                        detected = True
                        reason = "detected"
                        self._last_detected_at = now
                        self._consecutive_hits = 0
                else:
                    reason = "need_more_hits"
        else:
            self._consecutive_hits = 0
            self._prev_score = score

        if self.debug:
            _safe_log("[HOTWORD] audio_chunk_received=true")
            if self._last_prediction_keys:
                _safe_log(f"[HOTWORD] prediction_keys={self._last_prediction_keys} selected_key={self._last_prediction_key}")
            _safe_log(f"[HOTWORD] score={score:.4f}")
            _safe_log(f"[HOTWORD] threshold={self.threshold}")
            _safe_log(f"[HOTWORD] rms={rms:.5f}")
            _safe_log(f"[HOTWORD] prev_score={self._prev_score:.4f}")
            _safe_log(f"[HOTWORD] detected={str(detected).lower()}")
        return self._result(detected, score, start, reason)

    def _result(self, detected: bool, score: float, started_at: float, reason: str) -> HotwordResult:
        return HotwordResult(
            detected=detected,
            engine="openwakeword",
            phrase=self.phrase,
            score=score,
            threshold=self.threshold,
            latency_ms=max(0.0, (self._clock() - started_at) * 1000.0),
            reason=reason,
        )

    def reset(self) -> None:
        self._consecutive_hits = 0
        self._last_detected_at = 0.0
        self._prev_score = 0.0

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "engine": "openwakeword",
            "phrase": self.phrase,
            "phrases": self.phrases,
            "sample_rate": self.sample_rate,
            "frame_ms": self.frame_ms,
            "threshold": self.threshold,
            "consecutive_hits": self.consecutive_hits_required,
            "cooldown_ms": self.cooldown_ms,
            "model_path": os.path.basename(self.model_path) if self.model_path else "",
            "model_name": self._model_name,
            "load_error": self._load_error,
            "prediction_keys": list(self._last_prediction_keys),
            "selected_key": self._last_prediction_key,
            "min_rms": self.min_rms,
            "rising_edge_delta": self.rising_edge_delta,
            "max_score": self._max_score,
            "custom_hotword_required": self._score_frames >= 5 and self._max_score < 0.05,
        }

    def log_status(self) -> None:
        model_path_display = os.path.abspath(self.model_path) if self.model_path and os.path.isfile(self.model_path) else (self.pretrained if self.model_path else "bundled")
        _safe_log(f"[HOTWORD] enabled={str(self.enabled).lower()}")
        _safe_log(f"[HOTWORD] model_path={model_path_display}")
        _safe_log(f"[HOTWORD] sample_rate={self.sample_rate}")
        _safe_log(f"[HOTWORD] frame_ms={self.frame_ms}")
        _safe_log(f"[HOTWORD] threshold={self.threshold}")
        _safe_log(f"[HOTWORD] phrases={self.phrases}")
        _safe_log(f"[HOTWORD] selected_key={self.phrase}")
        _safe_log(f"[HOTWORD] min_rms={self.min_rms}")
        _safe_log(f"[HOTWORD] rising_edge_delta={self.rising_edge_delta}")
        _safe_log(f"[HOTWORD_CONFIG] threshold={self.threshold} consecutive_hits={self.consecutive_hits_required} min_rms={self.min_rms} rising_delta={self.rising_edge_delta} cooldown_ms={self.cooldown_ms}")
        _safe_log(f"[HOTWORD] model_name={self._model_name}")
        _safe_log(f"[HOTWORD] prediction_keys={self._last_prediction_keys}")
        _safe_log(f"[HOTWORD] selected_key={self._last_prediction_key}")
        if self._last_prediction_key and "hey jarvis" in self._last_prediction_key.lower() and "jarvis" in self.phrases.split(","):
            _safe_log("[HOTWORD] Note: only 'hey jarvis' key found in model. Standalone 'jarvis' requires custom model.")
            _safe_log("[HOTWORD] custom_hotword_required=true for 'jarvis' standalone")