import os

def _safe_log(msg: str) -> None:
    try:
        from engine.debug_trace import line
        line(msg)
    except Exception:
        print(msg, flush=True)


def _normalise_model_name(name: str) -> str:
    """Map a human phrase like 'hey nexi' to an openWakeWord model key 'hey_nexi'.

    Paths and explicit model files are returned untouched.
    """
    value = (name or "").strip()
    if not value:
        return ""
    if any(sep in value for sep in ("/", "\\")) or value.endswith((".onnx", ".tflite")):
        return value
    return value.replace(" ", "_").lower()


class OpenWakeWordScorer:
    """Wrapper for openwakeword.Model that loads a pretrained wake model.

    openWakeWord requires **16-bit PCM (int16)** audio frames. The model's
    feature extractor raises ``ValueError`` if anything else is passed, so this
    wrapper preserves the int16 contract end-to-end.
    """

    def __init__(self, model_path: str = "", pretrained: str = "hey_nexi"):
        self.name = "openwakeword"
        try:
            from openwakeword.model import Model as _OWWModel
            import numpy as np  # noqa: F401  (validated availability early)
        except ImportError as e:
            raise ImportError(f"openwakeword unavailable: {type(e).__name__}") from e

        self._model = None
        self.model_name = "unloaded"
        self._load_error = ""
        memory_exhausted = False

        # 1) Explicit custom model file wins.
        if model_path and os.path.exists(model_path):
            try:
                self._model = _OWWModel(wakeword_models=[model_path], inference_framework="onnx")
                self.model_name = os.path.basename(model_path)
                _safe_log(f"[OWW] model from path={self.model_name}")
            except Exception as e:
                self._load_error = f"{type(e).__name__}: {e}"
                _safe_log(f"[OWW] custom model load failed ({self._load_error})")
                memory_exhausted = isinstance(e, MemoryError)

        # 2) Otherwise load the pretrained model(s) by name. openWakeWord accepts
        #    short names like 'hey_nexi' and resolves them to the bundled ONNX.
        if self._model is None and not memory_exhausted:
            names = [_normalise_model_name(n) for n in (pretrained or "hey_nexi").split(",")]
            names = [n for n in names if n] or ["hey_nexi"]
            try:
                self._model = _OWWModel(wakeword_models=names, inference_framework="onnx")
                self.model_name = ",".join(self._model.models.keys()) or names[0]
                _safe_log(f"[OWW] model loaded names={list(self._model.models.keys())}")
            except Exception as e:
                # 3) Last resort: resolve the bundled .onnx path directly.
                self._load_error = f"{type(e).__name__}: {e}"
                if not isinstance(e, MemoryError):
                    try:
                        resolved = self._resolve_bundled_path(names[0])
                        self._model = _OWWModel(wakeword_models=[resolved], inference_framework="onnx")
                        self.model_name = ",".join(self._model.models.keys()) or os.path.basename(resolved)
                        _safe_log(f"[OWW] model loaded from bundled path={resolved}")
                    except Exception as e2:
                        self._load_error = f"{type(e2).__name__}: {e2}"
                        allow_download = (os.getenv("NEXI_OPENWAKEWORD_ALLOW_DOWNLOAD", "false") or "false").strip().lower() in {"1", "true", "yes", "on"}
                        if allow_download and not isinstance(e2, MemoryError):
                            try:
                                from openwakeword.utils import download_models
                                download_models()
                                self._model = _OWWModel(wakeword_models=names, inference_framework="onnx")
                                self.model_name = ",".join(self._model.models.keys()) or names[0]
                            except Exception as e3:
                                self._load_error = f"{type(e3).__name__}: {e3}"
                                self._model = None
                        if self._model is None:
                            _safe_log(f"[OWW] model load FAILED ({self._load_error}); scorer will report 0.0")

        self._last_prediction_keys: list[str] = []
        self._last_prediction_key: str = ""
        self._last_predictions: dict[str, float] = {}

    @staticmethod
    def _resolve_bundled_path(name: str) -> str:
        """Find the bundled ONNX file for a model name (e.g. 'hey_nexi')."""
        try:
            from importlib.resources import files
            base = files("openwakeword") / "resources" / "models"
            base_dir = str(base)
        except Exception:
            import openwakeword
            base_dir = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")

        candidates = [
            f"{name}.onnx",
            f"{name}_v0.1.onnx",
        ]
        # Also match any file that starts with the name (version-agnostic).
        try:
            for fname in os.listdir(base_dir):
                if fname.startswith(name) and fname.endswith(".onnx"):
                    candidates.append(fname)
        except Exception:
            pass

        for fname in candidates:
            full = os.path.join(base_dir, fname)
            if os.path.exists(full):
                return full
        raise FileNotFoundError(f"no bundled onnx for '{name}' under {base_dir}")

    def score(self, frame_int16: bytes) -> float:
        if self._model is None:
            return 0.0
        try:
            import numpy as np
            # openWakeWord requires 16-bit PCM samples (int16), NOT normalised floats.
            samples = np.frombuffer(frame_int16, dtype=np.int16)
            if samples.size == 0:
                return 0.0
            preds = self._model.predict(samples)
            if isinstance(preds, dict):
                cleaned = {str(k): float(v) for k, v in preds.items()}
                self._last_predictions = cleaned
                self._last_prediction_keys = sorted(cleaned.keys())
                if not cleaned:
                    self._last_prediction_key = ""
                    return 0.0
                selected_key = max(cleaned, key=cleaned.get)
                self._last_prediction_key = selected_key
                return float(cleaned.get(selected_key, 0.0))
            return float(preds)
        except MemoryError as e:
            self._load_error = f"MemoryError: {e}"
            self._model = None
            _safe_log("[OWW] score disabled reason=MemoryError")
            return 0.0
        except Exception as e:
            _safe_log(f"[OWW] score failed: {type(e).__name__}: {e}")
            return 0.0

    def get_debug_snapshot(self) -> dict:
        return {
            "model_name": self.model_name,
            "load_error": self._load_error,
            "prediction_keys": list(self._last_prediction_keys),
            "selected_key": self._last_prediction_key,
            "predictions": dict(self._last_predictions),
        }
