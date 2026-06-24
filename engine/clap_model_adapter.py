# clap_model_adapter.py
#
# Lazy adapter that wires CLAP_NN (external_tools/clap_nn_source/CLAP_NN)
# into Nexi runtime detection.
#
# Strategy: Option B from CLAP_NN_BATCH4_SOURCE_AUDIT.md.
#   - Reuse CLAP_NN preprocessing + inference logic when:
#       * CLAP_MODEL_PATH env var points to an existing .pth, AND
#       * torch / torchaudio / torchvision are importable.
#   - Anything missing -> raise CLAPModelUnavailable; caller falls back
#     to the RMS+peak signal detector in engine.clap_detector.
#
# No torch import happens at module import time. Everything is lazy so
# Nexi runs without PyTorch installed.

from __future__ import annotations

import io
import os
import sys
import wave

DEFAULT_SOURCE_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "external_tools",
        "clap_nn_source",
        "CLAP_NN",
    )
)


class CLAPModelUnavailable(Exception):
    """Raised when the CLAP_NN model path is unconfigured, the .pth is
    missing, or PyTorch / torchaudio / torchvision are not importable.
    Caller is expected to catch this and fall back to RMS detection."""


def _safe_log(msg: str) -> None:
    print(f"[CLAP_MODEL] {msg}")


def _resolve_model_path() -> str:
    return (os.getenv("CLAP_MODEL_PATH", "") or "").strip()


def _resolve_source_path() -> str:
    """Where CLAP_NN .py modules live. Defaults to the extracted zip path."""
    env = (os.getenv("CLAP_SOURCE_DIR", "") or "").strip()
    if env and os.path.isdir(env):
        return env
    if os.path.isdir(DEFAULT_SOURCE_PATH):
        return DEFAULT_SOURCE_PATH
    return ""


def is_model_available() -> bool:
    """Cheap predicate. True only if everything needed to call
    `ClapModelDetector(...)` is ready. Does not import torch."""
    model_path = _resolve_model_path()
    if not model_path or not os.path.exists(model_path):
        return False
    source_path = _resolve_source_path()
    if not source_path:
        return False
    try:
        import importlib.util
        for mod in ("torch", "torchaudio", "torchvision"):
            if importlib.util.find_spec(mod) is None:
                return False
    except Exception:
        return False
    return True


class ClapModelDetector:
    """Thin runtime adapter around CLAP_NN's AudioModelHandler.

    Use:
        det = ClapModelDetector()      # may raise CLAPModelUnavailable
        is_clap, conf = det.predict_pcm16(frame_bytes, sample_rate=16000)
    """

    CONFIDENCE_THRESHOLD = 0.99

    def __init__(self, model_path: str | None = None, source_path: str | None = None):
        model_path = (model_path or _resolve_model_path()).strip()
        if not model_path:
            raise CLAPModelUnavailable("CLAP_MODEL_PATH is not set")
        if not os.path.exists(model_path):
            raise CLAPModelUnavailable(f"model file not found: {model_path}")

        source_path = source_path or _resolve_source_path()
        if not source_path:
            raise CLAPModelUnavailable("CLAP_NN source directory not found")

        # Lazy heavy imports
        try:
            import torch  # noqa: F401
            import torchaudio  # noqa: F401
            from torchvision.transforms import Resize  # noqa: F401
        except ImportError as e:
            raise CLAPModelUnavailable(f"missing dependency: {e.name}") from None

        if source_path not in sys.path:
            sys.path.insert(0, source_path)

        try:
            from audio_inference import AudioModelHandler  # type: ignore
        except Exception as e:
            raise CLAPModelUnavailable(f"failed to import AudioModelHandler: {type(e).__name__}") from None

        try:
            self._handler = AudioModelHandler(model_path)
        except Exception as e:
            raise CLAPModelUnavailable(f"failed to load .pth: {type(e).__name__}") from None

        self._model_path = model_path
        self._source_path = source_path
        _safe_log(f"model_loaded path_ok=True source_ok=True")

    @property
    def model_path(self) -> str:
        return self._model_path

    @staticmethod
    def _pcm16_to_wav_bytes(frame_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Wrap a raw int16 mono PCM buffer in a minimal WAV container.
        torchaudio.load() requires a WAV/path; we use an in-memory file."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sample_rate)
            wf.writeframes(frame_bytes)
        return buf.getvalue()

    def predict_pcm16(self, frame_bytes: bytes, sample_rate: int = 16000) -> tuple[bool, float]:
        """Run CLAP_NN classification on a raw PCM16 mono frame.

        Returns (is_clap, confidence). confidence is in [0.0, 1.0].
        Errors are swallowed and return (False, 0.0) so the listener
        loop never crashes mid-stream.
        """
        try:
            import torch
            import tempfile

            wav_bytes = self._pcm16_to_wav_bytes(frame_bytes, sample_rate)
            # AudioModelHandler.transform_audio() takes a path. Write to
            # a temp file rather than monkey-patching torchaudio.load.
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                tmp_path = tmp.name
            try:
                spec = self._handler.transform_audio(tmp_path)
                with torch.no_grad():
                    logits = self._handler.model(spec)
                    probs = torch.softmax(logits, dim=1)
                    pred = int(torch.argmax(probs, dim=1).item())
                    conf = float(probs[0][pred].item())
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            is_clap = pred == 1 and conf >= self.CONFIDENCE_THRESHOLD
            return is_clap, conf
        except Exception as e:
            _safe_log(f"predict_failed reason={type(e).__name__}")
            return False, 0.0


def try_load_model_detector() -> ClapModelDetector | None:
    """Convenience for callers. Returns a working detector or None.
    Logs the reason for fallback exactly once."""
    if not is_model_available():
        _safe_log("model_unavailable reason=path_or_dep_missing using_fallback=rms")
        return None
    try:
        return ClapModelDetector()
    except CLAPModelUnavailable as e:
        _safe_log(f"model_unavailable reason={e} using_fallback=rms")
        return None
